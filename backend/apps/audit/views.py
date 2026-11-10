from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers

from apps.api.access import HasPermission

from .models import AuditEvent
from .serializers import AuditEventSerializer

FILTERS = ["actor_id", "action", "object_type", "object_id", "request_id"]


@extend_schema(
    parameters=[OpenApiParameter(f, str, required=False) for f in FILTERS]
    + [OpenApiParameter("from", str, required=False), OpenApiParameter("to", str, required=False)]
)
class AuditEventList(generics.ListAPIView):
    """Audit events, newest first. Read-only: there is no way to write through the API."""

    serializer_class = AuditEventSerializer
    permission_classes = [HasPermission]
    required_permission = "audit.view"

    def get_queryset(self):
        qs = AuditEvent.objects.all()
        params = self.request.query_params
        for name in FILTERS:
            if value := params.get(name):
                qs = qs.filter(**{name: value})
        for param, lookup in (("from", "at__gte"), ("to", "at__lt")):
            if raw := params.get(param):
                value = parse_datetime(raw)
                if value is None:
                    raise serializers.ValidationError({param: "Use an ISO 8601 date and time."})
                qs = qs.filter(**{lookup: value})
        return qs
