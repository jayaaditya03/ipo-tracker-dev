"""
URL routing.

One router registers every ViewSet, which generates the standard REST
routes (list, create, retrieve, update, destroy) plus any @action methods,
so the URL file stays short as the API grows.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from accounts.views import LoginView, MeView, PanProfileViewSet, RegisterView
from ipos.views import (
    ApplicationViewSet,
    DashboardSummaryView,
    IPOViewSet,
    RegistrarViewSet,
)

router = DefaultRouter()
router.register("pans", PanProfileViewSet, basename="pan")
router.register("ipos", IPOViewSet, basename="ipo")
router.register("applications", ApplicationViewSet, basename="application")
router.register("registrars", RegistrarViewSet, basename="registrar")

# basename is required because these ViewSets define get_queryset() rather
# than a class-level queryset — the router cannot introspect a model name
# from a method, so you name the route yourself.

auth_patterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("verify/", TokenVerifyView.as_view(), name="token-verify"),
    path("me/", MeView.as_view(), name="me"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include(auth_patterns)),
    path("api/dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("api/", include(router.urls)),
    # Session login for the browsable API — handy while developing.
    path("api-auth/", include("rest_framework.urls")),
]

if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]