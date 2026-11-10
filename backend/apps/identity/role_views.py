"""Role administration API (FR-04). Roles are data; the permission list is fixed in code."""

from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission

from . import services
from .catalogue import CATALOGUE
from .models import Role
from .serializers import PermissionSerializer, RoleSerializer


def _roles():
    return Role.objects.annotate(user_count=Count("assignments")).order_by("name")


def _out(role):
    return {
        "id": role.pk,
        "name": role.name,
        "description": role.description,
        "permissions": role.permissions,
        "scope_mode": role.scope_mode,
        "active": role.active,
        "is_system": role.is_system,
        "user_count": role.assignments.count(),
    }


def _run(fn, **kwargs):
    try:
        return fn(**kwargs)
    except services.AccessError as exc:
        raise serializers.ValidationError({exc.field: [exc.message]}) from exc


class PermissionCatalogueView(APIView):
    permission_classes = [HasPermission]
    required_permission = "identity.manage_roles"

    @extend_schema(responses=PermissionSerializer(many=True))
    def get(self, request):
        return Response(
            [
                {"code": p.code, "label": p.label, "group": p.group, "grant_only": p.grant_only}
                for p in CATALOGUE
            ]
        )


class RoleListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": "identity.manage_roles", "POST": "identity.manage_roles"}

    @extend_schema(responses=RoleSerializer(many=True))
    def get(self, request):
        return Response([_out(r) for r in _roles()])

    @extend_schema(request=RoleSerializer, responses={201: RoleSerializer})
    def post(self, request):
        data = RoleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        role = _run(services.create_role, actor=request.user, **data.validated_data)
        return Response(_out(role), status=status.HTTP_201_CREATED)


class RoleDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = "identity.manage_roles"

    @extend_schema(responses=RoleSerializer)
    def get(self, request, pk):
        return Response(_out(get_object_or_404(Role, pk=pk)))

    @extend_schema(request=RoleSerializer, responses=RoleSerializer)
    def patch(self, request, pk):
        role = get_object_or_404(Role, pk=pk)
        data = RoleSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        role = _run(services.update_role, actor=request.user, role=role, **data.validated_data)
        return Response(_out(role))

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        role = get_object_or_404(Role, pk=pk)
        _run(services.delete_role, actor=request.user, role=role)
        return Response(status=status.HTTP_204_NO_CONTENT)
