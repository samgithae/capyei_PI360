"""Restricted-permission grants API (SEC-18): who holds a grant-only permission, why, until when.
Needs ``identity.manage_roles`` because a grant widens what a person may see or take out."""

import datetime

from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission

from . import services
from .catalogue import BY_CODE, GRANT_ONLY
from .models import PermissionGrant

User = get_user_model()
MANAGE = "identity.manage_roles"
MAX_DAYS = 365


class GrantCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    permission = serializers.CharField(max_length=60)
    purpose = serializers.CharField(max_length=300)
    expires_on = serializers.DateField()  # the grant lasts until the end of this day

    def validate_expires_on(self, value):
        if value > timezone.localdate() + datetime.timedelta(days=MAX_DAYS):
            raise serializers.ValidationError(f"A grant can last at most {MAX_DAYS} days.")
        return value


def _out(g):
    now = timezone.now()
    state = "revoked" if g.revoked_at else "expired" if g.expires_at <= now else "active"
    return {
        "id": g.pk,
        "user": {"id": g.user_id, "username": g.user.username, "name": g.user.get_full_name()},
        "permission": g.permission,
        "label": BY_CODE[g.permission].label if g.permission in BY_CODE else g.permission,
        "purpose": g.purpose,
        "granted_by": g.granted_by.username if g.granted_by_id else "",
        "granted_at": g.granted_at,
        "expires_at": g.expires_at,
        "revoked_at": g.revoked_at,
        "state": state,
    }


def _all():
    return PermissionGrant.objects.select_related("user", "granted_by").order_by("-granted_at")


class GrantListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": MANAGE, "POST": MANAGE}

    @extend_schema(operation_id="grants_list", responses={200: dict})
    def get(self, request):
        return Response(
            {
                "grantable": [{"code": c, "label": BY_CODE[c].label} for c in sorted(GRANT_ONLY)],
                "max_days": MAX_DAYS,
                "results": [_out(g) for g in _all()[:200]],
            }
        )

    @extend_schema(
        operation_id="grants_create", request=GrantCreateSerializer, responses={201: dict}
    )
    def post(self, request):
        s = GrantCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        user = get_object_or_404(User, pk=d["user_id"], is_active=True)
        end = timezone.make_aware(
            datetime.datetime.combine(d["expires_on"], datetime.time(23, 59, 59))
        )
        try:
            g = services.grant_permission(
                actor=request.user,
                user=user,
                permission=d["permission"],
                purpose=d["purpose"],
                expires_at=end,
            )
        except services.AccessError as exc:
            raise serializers.ValidationError({exc.field: [exc.message]}) from exc
        return Response(_out(_all().get(pk=g.pk)), status=status.HTTP_201_CREATED)


class GrantRevokeView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": MANAGE}

    @extend_schema(
        operation_id="grants_revoke",
        request=serializers.Serializer,
        responses={200: dict},
    )
    def post(self, request, pk):
        g = get_object_or_404(_all(), pk=pk)
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise serializers.ValidationError({"reason": ["Say why the grant is withdrawn."]})
        services.revoke_grant(actor=request.user, grant=g, reason=reason)
        g.refresh_from_db()
        return Response(_out(g))
