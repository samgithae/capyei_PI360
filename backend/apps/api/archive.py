"""Shared API pieces for archive (soft delete): the bulk request body, a base view and the list
filter. The change itself is ``apps.audit.archive.set_archived`` (it writes the audit event)."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import HasPermission

ARCHIVE = "records.archive"
MAX_BULK = 200


class BulkSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=MAX_BULK, allow_empty=False
    )
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class BulkArchiveView(APIView):
    """POST {ids, reason?}. Subclasses set ``archive`` and implement ``run``."""

    permission_classes = [HasPermission]
    required_permission = {"POST": ARCHIVE}
    archive = True

    def run(self, request, ids, reason):
        """Archive or restore ``ids`` (self.archive) and return {changed, skipped}."""
        raise NotImplementedError

    @extend_schema(request=BulkSerializer, responses={200: dict})
    def post(self, request):
        s = BulkSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(self.run(request, s.validated_data["ids"], s.validated_data["reason"]))


def archived_filter(qs, params, prefix=""):
    """List filter: archived records are hidden unless ``?archived=1`` asks for only those."""
    return qs.filter(**{f"{prefix}archived_at__isnull": params.get("archived") != "1"})
