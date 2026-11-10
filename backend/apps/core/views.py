from django.conf import settings
from django.db import connection
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import HealthSerializer, MeSerializer


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


@method_decorator(ensure_csrf_cookie, name="get")
class MeView(APIView):
    """Who is signed in. Sets the CSRF cookie for the SPA (ADR-023).
    Roles and permissions arrive with the identity module (T-142)."""

    permission_classes = [AllowAny]

    @extend_schema(responses=MeSerializer)
    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"authenticated": False})
        return Response(
            {
                "authenticated": True,
                "username": user.get_username(),
                "roles": sorted(user.groups.values_list("name", flat=True)),
            }
        )
