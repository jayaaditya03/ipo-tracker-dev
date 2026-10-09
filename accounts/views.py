"""
Auth and PAN endpoints.
"""

from django.db.models import Count, Q
from rest_framework import generics, permissions, viewsets
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView

from .models import PanProfile
from .permissions import IsOwner
from .serializers import (
    EmailTokenObtainPairSerializer,
    PanProfileSerializer,
    RegisterSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    # The one endpoint that must be open — everything else inherits
    # IsAuthenticated from REST_FRAMEWORK settings.
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"


class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"


class LogoutView(TokenBlacklistView):
    """
    POST /api/auth/logout/ {"refresh": "..."} — revokes the refresh token,
    so the session ends on the server, not just in the browser. Open to
    anonymous callers because the access token may already have expired;
    holding the refresh token is the proof.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH the signed-in user. No pk in the URL — it comes from the token."""

    serializer_class = UserSerializer

    def get_object(self):
        return (
            type(self.request.user).objects
            .annotate(pan_count=Count("pans", filter=Q(pans__is_active=True)))
            .get(pk=self.request.user.pk)
        )


class PanProfileViewSet(viewsets.ModelViewSet):
    serializer_class = PanProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    filterset_fields = ["is_active"]
    search_fields = ["label"]
    ordering_fields = ["label", "created_at"]

    def get_queryset(self):
        """
        The single most important method in the API.

        Every row this view can ever touch — list, retrieve, update,
        destroy — comes from here. Scoping it to request.user is what makes
        the app multi-tenant. `PanProfile.objects.all()` here would let any
        user read and delete any other user's PANs by guessing an id.
        """
        return (
            PanProfile.objects
            .filter(owner=self.request.user)
            .annotate(application_count=Count("applications"))
            # Meta.ordering is dropped from GROUP BY queries, so restate it
            # or pagination order is undefined.
            .order_by("label")
        )

    def perform_destroy(self, instance):
        """
        Soft-delete when the PAN has history. Hard-deleting would cascade
        to its applications and silently rewrite the user's track record.
        """
        if instance.applications.exists():
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
        else:
            instance.delete()