from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services

# The service leaves out any section whose list permission the viewer lacks, and every number
# respects their record scope, so any signed-in user may call these.


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="reporting_dashboard",
        parameters=[OpenApiParameter("period", str)],
        responses={200: dict},
    )
    def get(self, request):
        return Response(
            services.dashboard(request.user, period=request.query_params.get("period", "90"))
        )


class DrilldownView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="reporting_drilldown",
        parameters=[OpenApiParameter(n, str) for n in ("key", "period", "offset", "page_size")],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        try:
            offset = max(int(g.get("offset", 0)), 0)
            size = min(max(int(g.get("page_size", 25)), 1), 100)
        except ValueError:
            offset, size = 0, 25
        out = services.drilldown(
            request.user, g.get("key", ""), period=g.get("period", "90"), offset=offset, size=size
        )
        if out is None:
            raise NotFound()
        return Response(out)


# --- De-identified exports (T-071) -------------------------------------------------------------

from django.http import HttpResponse  # noqa: E402
from rest_framework import serializers, status  # noqa: E402

from apps.api.access import HasPermission  # noqa: E402

from . import exports  # noqa: E402

EXPORT = "exports.deidentified"
CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class ExportSerializer(serializers.Serializer):
    dataset = serializers.CharField(max_length=40)
    format = serializers.CharField(max_length=10)


def _export_error(exc):
    code = {"not_found": 404, "expired": 410}.get(exc.code, status.HTTP_409_CONFLICT)
    return Response(
        {"errors": [{"field": exc.field, "message": exc.message, "code": exc.code}]}, status=code
    )


class ExportsView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": EXPORT, "POST": EXPORT}

    @extend_schema(operation_id="exports_overview", responses={200: dict})
    def get(self, request):
        return Response(exports.overview(request.user))

    @extend_schema(operation_id="exports_create", request=ExportSerializer, responses={201: dict})
    def post(self, request):
        s = ExportSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            log = exports.create(
                actor=request.user,
                dataset=s.validated_data["dataset"],
                file_format=s.validated_data["format"],
            )
        except exports.ExportError as exc:
            return _export_error(exc)
        return Response(exports.serialize(log), status=status.HTTP_201_CREATED)


class ExportDownloadView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": EXPORT}

    @extend_schema(operation_id="exports_download", responses={200: bytes})
    def get(self, request, pk):
        try:
            log, content = exports.download(actor=request.user, export_id=pk)
        except exports.ExportError as exc:
            return _export_error(exc)
        resp = HttpResponse(content, content_type=CONTENT_TYPES[log.file_format])
        resp["Content-Disposition"] = f'attachment; filename="{log.filename}"'
        resp["Cache-Control"] = "no-store"
        return resp


class TableExportSerializer(serializers.Serializer):
    format = serializers.CharField(max_length=10)
    purpose = serializers.CharField(max_length=300, allow_blank=True)


class TableExportView(APIView):
    """Export a list as filtered on screen. Filters travel in the query string, exactly as the
    list itself takes them; the format and purpose are in the body."""

    permission_classes = [HasPermission]
    required_permission = {"POST": "exports.identifiable"}

    @extend_schema(
        operation_id="exports_table",
        parameters=[OpenApiParameter(n, str) for n in exports.FILTER_KEYS],
        request=TableExportSerializer,
        responses={200: bytes},
    )
    def post(self, request, table):
        s = TableExportSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            log, content, name = exports.export_table(
                actor=request.user,
                dataset=table,
                params=request.query_params,
                file_format=s.validated_data["format"],
                purpose=s.validated_data["purpose"],
            )
        except exports.ExportError as exc:
            return _export_error(exc)
        resp = HttpResponse(content, content_type=exports.TABLE_CONTENT[log.file_format])
        resp["Content-Disposition"] = f'attachment; filename="{name}"'
        resp["Cache-Control"] = "no-store"
        resp["X-Export-Rows"] = str(log.row_count)
        return resp
