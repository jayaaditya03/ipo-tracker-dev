"""
IPO domain models.

The central design decision: an IPO is *global* data — one row for
"Meridian Speciality Chemicals", shared by every user of the app — while an
Application is *per-user*. That split is what lets one admin-maintained IPO
table serve everybody, and it is why Application carries its own `owner`
column rather than reaching the user through the IPO.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Registrar(models.Model):
    """
    The registrar and transfer agent that processes allotment for an issue
    — KFin, MUFG Intime, Bigshare and so on. Each has its own status-check
    page, which is what the frontend deep-links to.
    """

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    status_check_url = models.URLField(
        blank=True,
        help_text="Public allotment-status page for this registrar.",
    )
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "registrars"
        ordering = ["name"]

    def __str__(self):
        return self.name


class IPO(models.Model):
    """
    A public issue. Maintained centrally (admin or a seed command), read by
    every user.
    """

    class Board(models.TextChoices):
        MAINBOARD = "MAINBOARD", "Mainboard"
        SME = "SME", "SME"

    class Status(models.TextChoices):
        UPCOMING = "UPCOMING", "Upcoming"
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"
        ALLOTTED = "ALLOTTED", "Allotment out"
        LISTED = "LISTED", "Listed"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    name = models.CharField(max_length=200)
    symbol = models.CharField(max_length=20, blank=True, help_text="NSE/BSE ticker, once known.")
    registrar = models.ForeignKey(
        Registrar,
        on_delete=models.PROTECT,   # never silently orphan issues
        related_name="ipos",
    )
    board = models.CharField(max_length=10, choices=Board.choices, default=Board.MAINBOARD)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UPCOMING)

    # Money is DecimalField, never FloatField. Binary floats cannot
    # represent 0.1 exactly, so float arithmetic on rupees drifts.
    price_band_low = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    price_band_high = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    lot_size = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Shares per lot. Retail must bid in whole multiples of this.",
    )
    issue_size_cr = models.DecimalField(
        "issue size (₹ crore)", max_digits=12, decimal_places=2, null=True, blank=True,
    )

    open_date = models.DateField(null=True, blank=True)
    close_date = models.DateField(null=True, blank=True)
    allotment_date = models.DateField(null=True, blank=True)
    refund_date = models.DateField(null=True, blank=True)
    listing_date = models.DateField(null=True, blank=True)

    listing_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Price at listing. Used to compute realised gain.",
    )
    gmp = models.DecimalField(
        "grey market premium (₹)", max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Unofficial, indicative only.",
    )

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Entered by hand"
        NSE = "NSE", "Synced from NSE"

    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    dates_estimated = models.BooleanField(
        default=False,
        help_text="Allotment/listing dates were estimated from the SEBI T+3 timeline, "
                  "not published by the exchange.",
    )
    registrar_ref = models.CharField(
        max_length=80, blank=True,
        help_text="This issue's id on the registrar's own status page. Filled in automatically.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ipos"
        ordering = ["-open_date", "name"]
        indexes = [
            # The three columns every list query filters or sorts on.
            models.Index(fields=["status"]),
            models.Index(fields=["-close_date"]),
            models.Index(fields=["-allotment_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(close_date__gte=models.F("open_date")),
                name="ipo_closes_after_it_opens",
            ),
            # The sync keys on symbol, so it must be unique — but hand-entered
            # issues may not have one yet, hence the condition.
            models.UniqueConstraint(
                fields=["symbol"],
                condition=~models.Q(symbol=""),
                name="uniq_ipo_symbol_when_set",
            ),
        ]

    def __str__(self):
        return self.name

    # ------------------------------------------------------- derived

    @property
    def cutoff_price(self) -> Decimal | None:
        """
        Retail bids at cut-off, which means the upper band price. That is
        the figure used to compute the amount blocked.
        """
        return self.price_band_high

    @property
    def lot_amount(self) -> Decimal | None:
        """Rupees blocked by a single lot at cut-off."""
        if self.lot_size and self.cutoff_price:
            return Decimal(self.lot_size) * self.cutoff_price
        return None

    @property
    def listing_gain_pct(self) -> Decimal | None:
        if self.listing_price and self.cutoff_price:
            return ((self.listing_price - self.cutoff_price) / self.cutoff_price) * 100
        return None

    def derive_status(self) -> str:
        """
        Status implied by today's date. Kept as a stored column as well,
        because an issue can be withdrawn out of sequence and because
        filtering on a stored column uses an index — a computed property
        cannot.
        """
        today = timezone.localdate()
        if self.status == self.Status.WITHDRAWN:
            return self.status
        if self.listing_date and today >= self.listing_date:
            return self.Status.LISTED
        if self.allotment_date and today >= self.allotment_date:
            return self.Status.ALLOTTED
        if self.close_date and today > self.close_date:
            return self.Status.CLOSED
        if self.open_date and today >= self.open_date:
            return self.Status.OPEN
        return self.Status.UPCOMING


class Application(models.Model):
    """
    One user's bid for one IPO under one PAN.

    The unique constraint on (ipo, pan) is the point of the whole model: a
    PAN may be used for exactly one application per issue. That is a SEBI
    rule, and duplicate applications get all copies rejected — so enforcing
    it in the database rather than in a view is the correct call.
    """

    class Category(models.TextChoices):
        RETAIL = "RETAIL", "Retail"
        SHNI = "SHNI", "S-HNI (₹2–10L)"
        BHNI = "BHNI", "B-HNI (above ₹10L)"
        EMPLOYEE = "EMPLOYEE", "Employee"
        SHAREHOLDER = "SHAREHOLDER", "Shareholder"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Not applied"
        APPLIED = "APPLIED", "Applied"
        ALLOTTED = "ALLOTTED", "Allotted"
        PARTIAL = "PARTIAL", "Partially allotted"
        REJECTED = "REJECTED", "Not allotted"
        REFUNDED = "REFUNDED", "Refunded"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    # Statuses that mean the registrar has published a result.
    RESOLVED = {Status.ALLOTTED, Status.PARTIAL, Status.REJECTED, Status.REFUNDED}

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    ipo = models.ForeignKey(IPO, on_delete=models.CASCADE, related_name="applications")
    pan = models.ForeignKey("accounts.PanProfile", on_delete=models.CASCADE, related_name="applications")

    category = models.CharField(max_length=12, choices=Category.choices, default=Category.RETAIL)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    lots = models.PositiveSmallIntegerField(default=1)
    bid_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Price bid per share. Usually the cut-off price.",
    )

    shares_allotted = models.PositiveIntegerField(default=0)
    application_number = models.CharField(
        max_length=40, blank=True,
        help_text="From your broker. Some registrars accept it instead of a PAN.",
    )
    bank_reference = models.CharField(max_length=60, blank=True, help_text="ASBA / UPI mandate reference.")
    notes = models.TextField(blank=True)

    checked_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When allotment was last checked for this application.",
    )
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "applications"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["ipo", "pan"],
                name="uniq_application_per_pan_per_ipo",
            ),
            models.CheckConstraint(
                condition=models.Q(lots__gte=1),
                name="application_has_at_least_one_lot",
            ),
        ]
        indexes = [
            # Matches the dashboard's "my applications, newest first" query.
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["owner", "status"]),
        ]

    def __str__(self):
        return f"{self.pan.label} → {self.ipo.name} ({self.get_status_display()})"

    # ------------------------------------------------------- derived

    @property
    def shares_applied(self) -> int:
        return self.lots * (self.ipo.lot_size or 0)

    @property
    def amount_blocked(self) -> Decimal:
        """Rupees held by the ASBA mandate while the issue is in process."""
        return Decimal(self.shares_applied) * self.bid_price

    @property
    def amount_allotted(self) -> Decimal:
        return Decimal(self.shares_allotted) * self.bid_price

    @property
    def listing_gain(self) -> Decimal | None:
        """Realised gain if sold at the listing price."""
        if not self.shares_allotted or not self.ipo.listing_price:
            return None
        return Decimal(self.shares_allotted) * (self.ipo.listing_price - self.bid_price)

    @property
    def is_resolved(self) -> bool:
        return self.status in self.RESOLVED

    # -------------------------------------------------- transitions

    def mark_status(self, new_status: str, *, source: str = "MANUAL", note: str = "", shares: int | None = None):
        """
        Change status and record the change. Always go through this rather
        than assigning `.status` directly — the audit trail is the only way
        to answer "when did this become rejected, and who said so?".

        Caller is responsible for save(); this only mutates and queues the
        event so both can happen inside one transaction.
        """
        old = self.status
        if old == new_status and shares is None:
            return None

        self.status = new_status
        if shares is not None:
            self.shares_allotted = shares
        if new_status == self.Status.APPLIED and not self.applied_at:
            self.applied_at = timezone.now()
        if new_status in self.RESOLVED:
            self.checked_at = timezone.now()

        return StatusEvent(
            application=self,
            from_status=old,
            to_status=new_status,
            source=source,
            note=note,
        )


class StatusEvent(models.Model):
    """
    Append-only log of status changes on an application.

    Worth having for two reasons. It gives the UI an activity feed, and it
    is the honest way to handle the gap between "registrar says rejected"
    and "refund actually landed" — you keep both facts with their times
    instead of overwriting one with the other.
    """

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Entered by user"
        REGISTRAR = "REGISTRAR", "Read from registrar"
        SYSTEM = "SYSTEM", "Automatic"

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="events",
    )
    from_status = models.CharField(max_length=10, blank=True)
    to_status = models.CharField(max_length=10)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "status_events"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["application", "-created_at"])]

    def __str__(self):
        return f"{self.application_id}: {self.from_status or '—'} → {self.to_status}"