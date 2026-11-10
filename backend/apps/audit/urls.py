from django.urls import path

from .views import AuditEventList

urlpatterns = [path("audit/events", AuditEventList.as_view(), name="audit-events")]
