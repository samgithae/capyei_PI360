"""Staff account administration API (FR-03). Assigning roles and scopes needs the stronger
``identity.manage_roles`` permission because it can widen what a person may see."""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django_otp.plugins.otp_totp.models import TOTPDevice
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission

from . import services, users
from .serializers import (
    ReasonSerializer,
    UserCreateSerializer,
    UserRolesSerializer,
    UserScopesSerializer,
    UserSerializer,
    UserUpdateSerializer,
)

User = get_user_model()
VIEW, MANAGE, ROLES = "identity.view_users", "identity.manage_users", "identity.manage_roles"


def _out(user):
    enrolled = set(
        TOTPDevice.objects.filter(user=user, confirmed=True).values_list("user_id", flat=True)
    )
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "mfa_enrolled": user.pk in enrolled,
        "last_login": user.last_login,
        "roles": [
            {"id": a.role_id, "name": a.role.name, "active": a.role.active}
            for a in user.role_assignments.select_related("role").order_by("role__name")
        ],
        "scopes": [
            {"kind": s.kind, "value": s.value}
            for s in user.scope_assignments.order_by("kind", "value")
        ],
    }


def _run(fn, **kwargs):
    try:
        return fn(**kwargs)
    except services.AccessError as exc:
        raise serializers.ValidationError({exc.field: [exc.message]}) from exc


def _get(pk):
    return get_object_or_404(User, pk=pk)


class UserListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "POST": MANAGE}

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Matches username, name or email."),
            OpenApiParameter("active", bool),
        ],
        responses=UserSerializer(many=True),
    )
    def get(self, request):
        qs = User.objects.order_by("username")
        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )
        active = request.query_params.get("active")
        if active in ("true", "false"):
            qs = qs.filter(is_active=(active == "true"))
        return Response([_out(u) for u in qs[:500]])

    @extend_schema(request=UserCreateSerializer, responses={201: UserSerializer})
    def post(self, request):
        data = UserCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if v.get("roles") and not _can_assign_roles(request.user):
            raise serializers.ValidationError({"roles": ["You may not assign roles."]})
        user = _run(users.create_user, actor=request.user, **v)
        return Response(_out(user), status=status.HTTP_201_CREATED)


def _can_assign_roles(user):
    from apps.api.access import has_permission

    return has_permission(user, ROLES)


class UserDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "PATCH": MANAGE}

    @extend_schema(responses=UserSerializer)
    def get(self, request, pk):
        return Response(_out(_get(pk)))

    @extend_schema(request=UserUpdateSerializer, responses=UserSerializer)
    def patch(self, request, pk):
        user = _get(pk)
        data = UserUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        _run(users.update_user, actor=request.user, user=user, **data.validated_data)
        return Response(_out(user))


class _Action(APIView):
    permission_classes = [HasPermission]
    required_permission = MANAGE

    @extend_schema(request=ReasonSerializer, responses=UserSerializer)
    def post(self, request, pk):
        user = _get(pk)
        data = ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _run(self.do, actor=request.user, user=user, reason=data.validated_data["reason"])
        user.refresh_from_db()
        return Response(_out(user))


class UserSuspendView(_Action):
    do = staticmethod(users.suspend_user)


class UserReactivateView(_Action):
    do = staticmethod(users.reactivate_user)


class UserMfaResetView(_Action):
    do = staticmethod(users.reset_mfa)


class UserRolesView(APIView):
    permission_classes = [HasPermission]
    required_permission = ROLES

    @extend_schema(request=UserRolesSerializer, responses=UserSerializer)
    def put(self, request, pk):
        user = _get(pk)
        data = UserRolesSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _run(users.set_roles, actor=request.user, user=user, role_ids=data.validated_data["roles"])
        return Response(_out(user))


class UserScopesView(APIView):
    permission_classes = [HasPermission]
    required_permission = ROLES

    @extend_schema(request=UserScopesSerializer, responses=UserSerializer)
    def put(self, request, pk):
        user = _get(pk)
        data = UserScopesSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        scopes = [(s["kind"], s["value"]) for s in data.validated_data["scopes"]]
        _run(services.set_scopes, actor=request.user, user=user, scopes=scopes)
        return Response(_out(user))
