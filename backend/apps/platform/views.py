from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import HealthSerializer


class HealthView(APIView):
    """Liveness and database check for load balancers and the SPA."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(responses={200: HealthSerializer, 503: HealthSerializer})
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            db = "ok"
        except Exception:  # noqa: BLE001
            db = "unavailable"
        status = "ok" if db == "ok" else "degraded"
        return Response(
            {"status": status, "database": db, "version": settings.APP_VERSION},
            status=200 if status == "ok" else 503,
        )
