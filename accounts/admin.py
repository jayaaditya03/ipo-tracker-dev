from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import PanProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Django's UserAdmin references `username` in its fieldsets, so those have
    to be redeclared or the admin page raises FieldError on load.
    """

    ordering = ["email"]
    list_display = ["email", "full_name", "is_staff", "is_active", "created_at"]
    list_filter = ["is_staff", "is_active"]
    search_fields = ["email", "full_name"]
    readonly_fields = ["created_at", "last_login"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser",
                                    "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "created_at")}),
    )

    # The form shown when creating a user from the admin.
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "full_name", "password1", "password2"),
        }),
    )


@admin.register(PanProfile)
class PanProfileAdmin(admin.ModelAdmin):
    list_display = ["label", "pan_masked", "owner", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["label", "owner__email"]
    # Never editable by hand — they must stay consistent with each other,
    # which only set_pan() guarantees.
    readonly_fields = ["pan_masked", "pan_hash", "created_at", "updated_at"]
    exclude = ["pan_encrypted"]