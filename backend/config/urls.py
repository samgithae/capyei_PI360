from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [path("api/v1/", include("apps.api.urls"))]
if settings.ENABLE_ADMIN:
    urlpatterns.insert(0, path("admin/", admin.site.urls))

# JSON problem responses, not HTML pages, for unknown URLs and server errors.
handler404 = "apps.api.problems.not_found"
handler500 = "apps.api.problems.server_error"
