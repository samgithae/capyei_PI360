from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import access, services
from .serializers import MeSerializer


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
                "roles": services.role_names(user),
                "permissions": sorted(access.IdentityAccess().permissions(user)),
                "scope": access.scope_summary(user),
            }
        )
