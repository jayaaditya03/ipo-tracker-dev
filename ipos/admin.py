from django.contrib import admin

from .models import IPO, Application, Registrar, StatusEvent


@admin.register(Registrar)
class RegistrarAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "ipo_count"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]

    def get_queryset(self, request):
        # annotate once instead of counting per row — otherwise the list
        # page runs one COUNT query per registrar (the classic N+1).
        from django.db.models import Count
        return super().get_queryset(request).annotate(_ipo_count=Count("ipos"))

    @admin.display(description="IPOs", ordering="_ipo_count")
    def ipo_count(self, obj):
        return obj._ipo_count


class ApplicationInline(admin.TabularInline):
    model = Application
    extra = 0
    fields = ["owner", "pan", "category", "lots", "bid_price", "status", "shares_allotted"]
    autocomplete_fields = ["owner", "pan"]
    show_change_link = True


@admin.register(IPO)
class IPOAdmin(admin.ModelAdmin):
    list_display = ["name", "board", "status", "registrar",
                    "price_band_high", "lot_size", "close_date", "allotment_date"]
    list_filter = ["board", "status", "registrar"]
    search_fields = ["name", "symbol"]
    date_hierarchy = "open_date"
    list_select_related = ["registrar"]      # avoids an N+1 on the list page
    inlines = [ApplicationInline]

    fieldsets = (
        (None, {"fields": ("name", "symbol", "registrar", "board", "status")}),
        ("Pricing", {"fields": ("price_band_low", "price_band_high", "lot_size",
                                "issue_size_cr", "gmp")}),
        ("Timeline", {"fields": ("open_date", "close_date", "allotment_date",
                                 "refund_date", "listing_date")}),
        ("Listing", {"fields": ("listing_price",)}),
    )

    actions = ["refresh_status", "sync_from_nse"]

    @admin.action(description="Sync all IPOs from NSE now (selection is ignored)")
    def sync_from_nse(self, request, queryset):
        from .sources.nse import NSEError
        from .sources.sync import sync_from_nse
        try:
            r = sync_from_nse()
        except NSEError as exc:
            self.message_user(request, f"NSE sync failed: {exc}", level="error")
            return
        self.message_user(request, f"NSE sync: {len(r.created)} created, {len(r.updated)} updated, "
                                   f"{r.unchanged} unchanged, {len(r.errors)} errors.")

    @admin.action(description="Recalculate status from today's date")
    def refresh_status(self, request, queryset):
        updated = 0
        for ipo in queryset:
            new = ipo.derive_status()
            if new != ipo.status:
                ipo.status = new
                ipo.save(update_fields=["status", "updated_at"])
                updated += 1
        self.message_user(request, f"Updated {updated} issue(s).")


class StatusEventInline(admin.TabularInline):
    model = StatusEvent
    extra = 0
    readonly_fields = ["from_status", "to_status", "source", "note", "created_at"]
    can_delete = False       # append-only log


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["ipo", "pan", "owner", "category", "lots",
                    "status", "shares_allotted", "created_at"]
    list_filter = ["status", "category", "ipo__board"]
    search_fields = ["ipo__name", "pan__label", "owner__email", "application_number"]
    list_select_related = ["ipo", "pan", "owner"]
    autocomplete_fields = ["ipo", "pan", "owner"]
    readonly_fields = ["created_at", "updated_at", "checked_at", "applied_at"]
    inlines = [StatusEventInline]


@admin.register(StatusEvent)
class StatusEventAdmin(admin.ModelAdmin):
    list_display = ["application", "from_status", "to_status", "source", "created_at"]
    list_filter = ["source", "to_status"]
    list_select_related = ["application", "application__ipo"]

    def has_add_permission(self, request):
        return False        # events are written by code, not by hand

    def has_change_permission(self, request, obj=None):
        return False