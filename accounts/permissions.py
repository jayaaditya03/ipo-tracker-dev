"""
Object-level permissions.

Scoping get_queryset() by request.user is the primary defence and is
usually enough — a row the queryset never returns cannot be fetched,
updated or deleted. This permission is defence in depth for any view that
looks an object up some other way.
"""

from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """Allow access only to objects whose `owner` is the requesting user."""

    message = "You do not have access to this record."

    def has_object_permission(self, request, view, obj):
        return getattr(obj, "owner_id", None) == request.user.id


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Writes restricted to the owner; reads allowed to any authenticated
    user. Used for shared reference data such as IPOs.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(obj, "owner_id", None) == request.user.id