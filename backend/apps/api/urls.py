"""/api/v1 routes. Each module contributes its own urls module; new major
versions get a new prefix and run side by side (doc 04 CMP-02)."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns = [
    path("", include("apps.platform.urls")),
    path("", include("apps.identity.urls")),
    path("", include("apps.audit.urls")),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
]
