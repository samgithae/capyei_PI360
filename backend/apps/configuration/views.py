"""Configuration API: reference data (T-057), feature flags and protected settings (T-039)."""

import uuid

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission

from . import services
from .models import FeatureFlag
from .reference import KINDS
from .serializers import (
    AliasSerializer,
    FlagSerializer,
    ReferenceInputSerializer,
    ReferenceReasonSerializer,
    SettingChangeSerializer,
    SettingSerializer,
)

VIEW, MANAGE, PROTECTED, REFERENCE = (
    "config.view",
    "config.manage",
    "config.manage_protected",
    "reference.manage",
)


def _run(fn, **kwargs):
    try:
        return fn(**kwargs)
    except services.ConfigError as exc:
        raise serializers.ValidationError({exc.field: [exc.message]}) from exc


def _kind(key):
    if key not in KINDS:
        raise NotFound("Unknown reference kind.")
    return KINDS[key]


def _obj(key, pk):
    kind = _kind(key)
    try:
        return kind.model.objects.get(pk=uuid.UUID(str(pk)))
    except (ValueError, kind.model.DoesNotExist):
        raise NotFound from None


def _out(key, obj):
    kind = KINDS[key]
    row = {"id": str(obj.pk), "active": obj.active}
    if kind.named:
        row.update(code=obj.code, name=obj.name)
    for f in kind.fields:
        v = getattr(obj, f)
        row[f] = v if v is None or isinstance(v, (int, bool)) else str(v)
    for f in kind.fks:
        v = getattr(obj, f + "_id")
        row[f] = None if v is None else str(v)
    return row


class ReferenceListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "POST": REFERENCE}

    @extend_schema(operation_id="config_reference_list", request=None, responses={200: dict})
    def get(self, request, kind):
        spec = _kind(kind)
        qs = spec.model.objects.all()
        if request.query_params.get("active") in ("true", "false"):
            qs = qs.filter(active=request.query_params["active"] == "true")
        for fk in spec.fks:  # ?county=<id> style filters
            if fk in request.query_params:
                qs = qs.filter(**{fk + "_id": request.query_params[fk]})
        q = request.query_params.get("q", "").strip()
        if q and spec.named:
            qs = qs.filter(name__icontains=q)
        qs = qs.order_by("name" if spec.named else "pk")
        return Response([_out(kind, o) for o in qs[:3000]])

    @extend_schema(request=ReferenceInputSerializer, responses={201: dict})
    def post(self, request, kind):
        _kind(kind)
        obj = _run(services.create_reference, actor=request.user, key=kind, data=request.data)
        return Response(_out(kind, obj), status=status.HTTP_201_CREATED)


class ReferenceDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "PATCH": REFERENCE}

    @extend_schema(operation_id="config_reference_detail", responses={200: dict})
    def get(self, request, kind, pk):
        return Response(_out(kind, _obj(kind, pk)))

    @extend_schema(request=ReferenceInputSerializer, responses={200: dict})
    def patch(self, request, kind, pk):
        obj = _run(
            services.update_reference,
            actor=request.user,
            key=kind,
            obj=_obj(kind, pk),
            data=request.data,
        )
        return Response(_out(kind, obj))


class _ReferenceActive(APIView):
    permission_classes = [HasPermission]
    required_permission = REFERENCE
    active = True

    @extend_schema(request=ReferenceReasonSerializer, responses={200: dict})
    def post(self, request, kind, pk):
        body = ReferenceReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        obj = _run(
            services.set_reference_active,
            actor=request.user,
            key=kind,
            obj=_obj(kind, pk),
            active=self.active,
            reason=body.validated_data["reason"],
        )
        return Response(_out(kind, obj))


class ReferenceDeactivateView(_ReferenceActive):
    active = False


class ReferenceReactivateView(_ReferenceActive):
    active = True


class ReferenceAliasView(APIView):
    permission_classes = [HasPermission]
    required_permission = REFERENCE

    @extend_schema(request=AliasSerializer, responses={201: dict})
    def post(self, request, kind, pk):
        body = AliasSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        row = _run(
            services.add_alias,
            actor=request.user,
            key=kind,
            obj=_obj(kind, pk),
            **body.validated_data,
        )
        return Response({"alias": row.alias}, status=status.HTTP_201_CREATED)


def _flag_out(f):
    return {
        "key": f.key,
        "description": f.description,
        "enabled": f.enabled,
        "environments": f.environments,
        "roles": f.roles,
    }


class FlagListView(APIView):
    permission_classes = [HasPermission]
    required_permission = VIEW

    @extend_schema(responses=FlagSerializer(many=True))
    def get(self, request):
        return Response([_flag_out(f) for f in FeatureFlag.objects.order_by("key")])


class FlagDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = MANAGE

    @extend_schema(request=FlagSerializer, responses=FlagSerializer)
    def patch(self, request, key):
        body = FlagSerializer(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        d = body.validated_data
        flag = services.set_flag(
            actor=request.user,
            key=key,
            enabled=d.get("enabled"),
            environments=d.get("environments"),
            roles=d.get("roles"),
            description=d.get("description"),
            reason=d.get("reason", ""),
        )
        return Response(_flag_out(flag))


class SettingListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "POST": PROTECTED}

    @extend_schema(responses=SettingSerializer(many=True))
    def get(self, request):
        return Response(
            [
                {
                    "key": k,
                    "label": s["label"],
                    "value": services.get_setting(k),
                    "default": s["default"],
                    "min": s["min"],
                    "max": s["max"],
                }
                for k, s in services.SETTINGS.items()
            ]
        )

    @extend_schema(request=SettingChangeSerializer, responses={204: None})
    def post(self, request):
        body = SettingChangeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        _run(services.change_setting, actor=request.user, **body.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)
