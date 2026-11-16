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
