"""
IPO and application endpoints.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsOwner

from .allotment.service import CHECKABLE, check_applications
from .models import IPO, Application, Registrar, StatusEvent
from .serializers import (
    ApplicationSerializer,
    BulkApplySerializer,
    IPODetailSerializer,
    IPOListSerializer,
    RegistrarSerializer,
    StatusEventSerializer,
)
from .sources.nse import NSEError
from .sources.sync import sync_from_nse

MONEY = DecimalField(max_digits=16, decimal_places=2)

# Most PANs one request will check. At ~1 request/second per registrar
# this keeps the call well under typical proxy timeouts.
CHECK_LIMIT = 25


class RegistrarViewSet(viewsets.ReadOnlyModelViewSet):
    """Reference data. Read-only through the API; maintained in the admin."""

    queryset = Registrar.objects.filter(is_active=True)
    serializer_class = RegistrarSerializer
    pagination_class = None       # short list, no point paginating


class IPOViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Shared IPO catalogue. Every authenticated user sees the same rows, so
    there is no per-user scoping here — unlike applications.
    """

    serializer_class = IPOListSerializer
    filterset_fields = ["board", "status", "registrar__slug"]
    search_fields = ["name", "symbol"]
    ordering_fields = ["open_date", "close_date", "allotment_date", "listing_date", "name"]
    ordering = ["-open_date"]

    def get_queryset(self):
        qs = IPO.objects.select_related("registrar")
        if self.request.user.is_authenticated:
            # One annotated query instead of one extra query per row.
            qs = qs.annotate(
                _my_application_count=Count(
                    "applications",
                    filter=Q(applications__owner=self.request.user),
                    distinct=True,
                )
            )
        return qs

    def get_serializer_class(self):
        # Lean payload for lists, full payload for a single record.
        return IPODetailSerializer if self.action == "retrieve" else IPOListSerializer

    @action(detail=False, methods=["get"])
    def open_now(self, request):
        """GET /api/ipos/open_now/ — issues accepting bids today."""
        today = timezone.localdate()
        qs = self.get_queryset().filter(open_date__lte=today, close_date__gte=today)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=False, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def sync(self, request):
        """POST /api/ipos/sync/ — staff only. Pulls the latest issues from NSE."""
        try:
            r = sync_from_nse()
        except NSEError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"created": len(r.created), "updated": len(r.updated),
                         "unchanged": r.unchanged, "errors": r.errors})


class ApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    filterset_fields = ["status", "category", "ipo", "pan", "ipo__board"]
    search_fields = ["ipo__name", "pan__label", "application_number"]
    ordering_fields = ["created_at", "ipo__allotment_date", "lots"]
    ordering = ["-created_at"]

    def get_queryset(self):
        # Scoped to the requesting user. select_related collapses what
        # would otherwise be three extra queries per row into one JOIN.
        return (
            Application.objects
            .filter(owner=self.request.user)
            .select_related("ipo", "ipo__registrar", "pan")
        )

    # ------------------------------------------------------- actions

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """
        POST /api/applications/bulk/

        Apply to one IPO across several PANs in a single round trip —
        the thing this app exists to make easy.

        Per-row results rather than all-or-nothing: if one PAN already has
        an application for this issue, that row is reported as skipped and
        the rest still succeed.
        """
        serializer = BulkApplySerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        ipo = data["ipo"]
        lots = data["lots"]
        bid_price = ipo.cutoff_price or Decimal("0")
        if not bid_price:
            return Response(
                {"detail": "This issue has no price band yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_status = Application.Status.APPLIED if data["mark_applied"] else Application.Status.DRAFT
        created, skipped = [], []

        for pan in data["pans"]:
            try:
                # Each row gets its own savepoint. Without it, an
                # IntegrityError would poison the outer transaction and
                # every later row would fail too.
                with transaction.atomic():
                    app = Application.objects.create(
                        owner=request.user,
                        ipo=ipo,
                        pan=pan,
                        category=data["category"],
                        lots=lots,
                        bid_price=bid_price,
                        status=new_status,
                        applied_at=timezone.now() if data["mark_applied"] else None,
                    )
                    StatusEvent.objects.create(
                        application=app,
                        from_status="",
                        to_status=new_status,
                        source=StatusEvent.Source.MANUAL,
                        note="Created via bulk apply.",
                    )
                created.append(app)
            except IntegrityError:
                # The unique constraint did its job.
                skipped.append({
                    "pan_id": pan.id,
                    "pan_label": pan.label,
                    "reason": "An application already exists for this PAN and issue.",
                })

        return Response(
            {
                "created": ApplicationSerializer(
                    created, many=True, context={"request": request}
                ).data,
                "skipped": skipped,
                "summary": {
                    "requested": len(data["pans"]),
                    "created": len(created),
                    "skipped": len(skipped),
                },
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"])
    def check(self, request):
        """
        POST /api/applications/check/
        Body (all optional): {"ipo_id": 12} or {"application_ids": [1, 2]}

        Asks each registrar for the allotment result of every matching PAN
        and records the answers. With no body, checks every pending
        application whose allotment date has arrived. Capped per request so
        one call can't hammer a registrar.
        """
        qs = self.get_queryset().exclude(status=Application.Status.DRAFT)
        ids = request.data.get("application_ids")
        ipo_id = request.data.get("ipo_id")
        if ids:
            qs = qs.filter(id__in=ids)
        else:
            qs = qs.filter(status__in=CHECKABLE)
            if ipo_id:
                qs = qs.filter(ipo_id=ipo_id)
            else:
                qs = qs.filter(Q(ipo__allotment_date__isnull=True)
                               | Q(ipo__allotment_date__lte=timezone.localdate()))

        rows = check_applications(qs.order_by("ipo_id", "id")[:CHECK_LIMIT])
        summary = {}
        for r in rows:
            summary[r["outcome"]] = summary.get(r["outcome"], 0) + 1
        return Response({"results": rows, "summary": summary})

    @action(detail=True, methods=["post"])
    def set_status(self, request, pk=None):
        """
        POST /api/applications/{id}/set_status/
        Body: {"status": "ALLOTTED", "shares_allotted": 43, "note": "..."}

        Goes through mark_status() so the change is logged. Status and its
        audit event are written in one transaction — you cannot end up with
        one without the other.
        """
        application = self.get_object()
        new_status = request.data.get("status")

        valid = dict(Application.Status.choices)
        if new_status not in valid:
            return Response(
                {"status": f"Must be one of: {', '.join(valid)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shares = request.data.get("shares_allotted")
        if shares is not None:
            try:
                shares = int(shares)
            except (TypeError, ValueError):
                return Response({"shares_allotted": "Must be a whole number."},
                                status=status.HTTP_400_BAD_REQUEST)
            if shares > application.shares_applied:
                return Response(
                    {"shares_allotted": f"Cannot exceed the {application.shares_applied} shares applied for."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif new_status == Application.Status.ALLOTTED:
            shares = application.shares_applied      # full allotment
        elif new_status in (Application.Status.REJECTED, Application.Status.REFUNDED):
            shares = 0

        with transaction.atomic():
            event = application.mark_status(
                new_status,
                source=StatusEvent.Source.MANUAL,
                note=request.data.get("note", ""),
                shares=shares,
            )
            application.save()
            if event:
                event.save()

        return Response(self.get_serializer(application).data)

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        """GET /api/applications/{id}/events/ — the audit trail."""
        application = self.get_object()
        return Response(
            StatusEventSerializer(application.events.all(), many=True).data
        )


class DashboardSummaryView(APIView):
    """
    GET /api/dashboard/summary/

    Every figure here is computed by the database in two aggregate
    queries. The naive version — loop the applications in Python and add
    up amount_blocked — issues one query per row and gets slower as the
    user's history grows. This does not.
    """

    def get(self, request):
        qs = Application.objects.filter(owner=request.user)

        # F() references a column, so the multiplication happens in SQL.
        amount = F("lots") * F("ipo__lot_size") * F("bid_price")
        allotted_amount = F("shares_allotted") * F("bid_price")

        totals = qs.aggregate(
            applications=Count("id", filter=~Q(status=Application.Status.DRAFT)),
            drafts=Count("id", filter=Q(status=Application.Status.DRAFT)),
            pending=Count("id", filter=Q(status=Application.Status.APPLIED)),
            allotted=Count("id", filter=Q(status__in=[
                Application.Status.ALLOTTED, Application.Status.PARTIAL,
            ])),
            rejected=Count("id", filter=Q(status__in=[
                Application.Status.REJECTED, Application.Status.REFUNDED,
            ])),
            # Coalesce turns a NULL sum (no matching rows) into 0, so the
            # frontend never has to handle null.
            blocked=Coalesce(
                Sum(amount, filter=Q(status=Application.Status.APPLIED), output_field=MONEY),
                Value(Decimal("0")), output_field=MONEY,
            ),
            invested=Coalesce(
                Sum(allotted_amount, filter=Q(status__in=[
                    Application.Status.ALLOTTED, Application.Status.PARTIAL,
                ]), output_field=MONEY),
                Value(Decimal("0")), output_field=MONEY,
            ),
        )

        resolved = totals["allotted"] + totals["rejected"]
        totals["hit_rate"] = round(totals["allotted"] / resolved * 100, 1) if resolved else 0.0

        # Realised gain, only where a listing price is known.
        gain = qs.filter(
            status__in=[Application.Status.ALLOTTED, Application.Status.PARTIAL],
            ipo__listing_price__isnull=False,
        ).aggregate(
            total=Coalesce(
                Sum(F("shares_allotted") * (F("ipo__listing_price") - F("bid_price")),
                    output_field=MONEY),
                Value(Decimal("0")), output_field=MONEY,
            )
        )
        totals["realised_gain"] = gain["total"]

        totals["by_pan"] = list(
            qs.exclude(status=Application.Status.DRAFT)
              .values("pan__id", "pan__label")
              .annotate(
                  applications=Count("id"),
                  allotted=Count("id", filter=Q(status__in=[
                      Application.Status.ALLOTTED, Application.Status.PARTIAL,
                  ])),
              )
              .order_by("-applications")
        )

        return Response(totals)