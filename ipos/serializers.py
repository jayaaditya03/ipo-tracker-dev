"""
Serializers for registrars, IPOs and applications.

A recurring pattern here: nested object on read, plain id on write. The
frontend wants `application.ipo.name` without a second request, but
posting a whole nested IPO to create an application would be absurd. So
read fields use a nested serializer and write fields use
PrimaryKeyRelatedField under a `*_id` name.
"""

from decimal import Decimal

from rest_framework import serializers

from accounts.models import PanProfile

from .models import IPO, Application, Registrar, StatusEvent


class RegistrarSerializer(serializers.ModelSerializer):
    class Meta:
        model = Registrar
        fields = ["id", "name", "slug", "status_check_url", "website"]


class IPOListSerializer(serializers.ModelSerializer):
    """Lean payload for the list view."""

    registrar = RegistrarSerializer(read_only=True)
    cutoff_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    lot_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = IPO
        fields = [
            "id", "name", "symbol", "board", "status", "registrar",
            "price_band_low", "price_band_high", "cutoff_price",
            "lot_size", "lot_amount", "gmp", "listing_price",
            "open_date", "close_date", "allotment_date", "listing_date", "dates_estimated",
        ]


class IPODetailSerializer(IPOListSerializer):
    """
    Everything in the list payload plus the heavier fields, and whether
    *this* user has already applied — which is what the Apply button needs
    to know.
    """

    listing_gain_pct = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    my_application_count = serializers.SerializerMethodField()

    class Meta(IPOListSerializer.Meta):
        fields = IPOListSerializer.Meta.fields + [
            "issue_size_cr", "refund_date",
            "listing_gain_pct", "my_application_count", "created_at",
        ]

    def get_my_application_count(self, obj) -> int:
        # Set by the view's annotation where available; falls back to a
        # query so the serializer still works outside that view.
        if hasattr(obj, "_my_application_count"):
            return obj._my_application_count
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0
        return obj.applications.filter(owner=request.user).count()


class IPOPricesSerializer(serializers.ModelSerializer):
    """Staff edit of the two figures NSE does not publish in its IPO feed."""

    class Meta:
        model = IPO
        fields = ["listing_price", "gmp"]
        extra_kwargs = {"listing_price": {"min_value": Decimal("0.01")}}


class StatusEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatusEvent
        fields = ["id", "from_status", "to_status", "source", "note", "created_at"]
        read_only_fields = fields


class ApplicationSerializer(serializers.ModelSerializer):
    ipo = IPOListSerializer(read_only=True)
    ipo_id = serializers.PrimaryKeyRelatedField(
        source="ipo", queryset=IPO.objects.all(), write_only=True,
    )
    pan_label = serializers.CharField(source="pan.label", read_only=True)
    pan_masked = serializers.CharField(source="pan.pan_masked", read_only=True)
    # The queryset here is replaced per-request in __init__ — see below.
    # Readable too, so the client can match applications to PANs by id.
    pan_id = serializers.PrimaryKeyRelatedField(
        source="pan", queryset=PanProfile.objects.none(),
    )

    shares_applied = serializers.IntegerField(read_only=True)
    amount_blocked = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    listing_gain = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    expected_gain = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Application
        fields = [
            "id", "ipo", "ipo_id", "pan_id", "pan_label", "pan_masked",
            "category", "status", "status_display", "lots", "bid_price",
            "shares_applied", "amount_blocked", "shares_allotted", "listing_gain", "expected_gain",
            "application_number", "bank_reference", "notes",
            "applied_at", "checked_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "applied_at", "checked_at", "created_at", "updated_at"]
        # Optional on input: validate() defaults it to the cut-off price.
        extra_kwargs = {"bid_price": {"required": False}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Narrow the pan_id queryset to the requesting user's own PANs.
        # Without this, a user could post someone else's pan_id and create
        # an application against a PAN they do not own — DRF would happily
        # accept it, because the default queryset is "all PANs".
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["pan_id"].queryset = PanProfile.objects.filter(
                owner=request.user, is_active=True,
            )

    def validate(self, attrs):
        ipo = attrs.get("ipo") or getattr(self.instance, "ipo", None)
        lots = attrs.get("lots", getattr(self.instance, "lots", 1))

        if ipo and ipo.status in (IPO.Status.WITHDRAWN,):
            raise serializers.ValidationError({"ipo_id": "This issue has been withdrawn."})

        # Default the bid to cut-off rather than making the client send it.
        if not attrs.get("bid_price") and not self.instance:
            if not ipo or not ipo.cutoff_price:
                raise serializers.ValidationError(
                    {"bid_price": "This issue has no price band yet, so a bid price is required."}
                )
            attrs["bid_price"] = ipo.cutoff_price

        # Retail is capped at ₹2 lakh per application by SEBI. Catching it
        # here is friendlier than letting the bank reject the mandate.
        category = attrs.get("category", getattr(self.instance, "category", Application.Category.RETAIL))
        if category == Application.Category.RETAIL and ipo and ipo.lot_size:
            amount = Decimal(lots * ipo.lot_size) * attrs.get(
                "bid_price", getattr(self.instance, "bid_price", Decimal("0"))
            )
            if amount > Decimal("200000"):
                raise serializers.ValidationError({
                    "lots": f"₹{amount:,.0f} exceeds the ₹2,00,000 retail limit. "
                            f"Use the S-HNI category for a larger bid."
                })
        return attrs

    def create(self, validated_data):
        # owner comes from the token, never from the request body —
        # otherwise a client could create rows owned by someone else.
        validated_data["owner"] = self.context["request"].user
        return super().create(validated_data)


class CheckPansSerializer(serializers.Serializer):
    """Input for POST /api/applications/check_pans/ — ask about any issue, past or present."""

    ipo_id = serializers.PrimaryKeyRelatedField(source="ipo", queryset=IPO.objects.all())
    pan_ids = serializers.PrimaryKeyRelatedField(
        source="pans", queryset=PanProfile.objects.none(), many=True, allow_empty=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["pan_ids"].child_relation.queryset = PanProfile.objects.filter(owner=request.user)


class BulkApplySerializer(serializers.Serializer):
    """
    Input for POST /api/applications/bulk/ — apply to one IPO across
    several PANs in a single request.

    A plain Serializer, not a ModelSerializer: the input shape is not a
    model, it is a command.
    """

    ipo_id = serializers.PrimaryKeyRelatedField(source="ipo", queryset=IPO.objects.all())
    pan_ids = serializers.PrimaryKeyRelatedField(
        source="pans", queryset=PanProfile.objects.none(), many=True,
    )
    category = serializers.ChoiceField(
        choices=Application.Category.choices, default=Application.Category.RETAIL,
    )
    lots = serializers.IntegerField(min_value=1, default=1)
    mark_applied = serializers.BooleanField(
        default=True,
        help_text="Record these as submitted rather than as drafts.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["pan_ids"].child_relation.queryset = PanProfile.objects.filter(
                owner=request.user, is_active=True,
            )

    def validate_pan_ids(self, value):
        if not value:
            raise serializers.ValidationError("Select at least one PAN.")
        return value

    def validate(self, attrs):
        # Same ₹2 lakh retail cap as single applications — bulk apply must
        # not be a way around it.
        ipo = attrs["ipo"]
        if attrs["category"] == Application.Category.RETAIL and ipo.lot_size and ipo.cutoff_price:
            amount = Decimal(attrs["lots"] * ipo.lot_size) * ipo.cutoff_price
            if amount > Decimal("200000"):
                raise serializers.ValidationError({
                    "lots": f"₹{amount:,.0f} per PAN exceeds the ₹2,00,000 retail limit."
                })
        if ipo.status == IPO.Status.WITHDRAWN:
            raise serializers.ValidationError({"ipo_id": "This issue has been withdrawn."})
        return attrs