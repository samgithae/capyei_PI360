"""Support intervention API (T-064, FR-21). referrals.view reads, referrals.edit works
interventions, caseload.reassign hands one to another officer.

An intervention whose youth is outside the caller's scope gives 404."""

import uuid

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission, has_permission
from apps.api.pagination import page_size_of
from apps.audit import services as audit

from . import services
from .models import Intervention
from .views import EDIT, REASSIGN, VIEW, _violation

STATUS_NAMES = dict(Intervention.STATUSES)
NEED_NAMES = dict(Intervention.NEEDS)
SOURCE_NAMES = dict(Intervention.SOURCES)


def _user_name(u):
    return (u.get_full_name() or u.get_username()) if u else ""


def _summary(i, today):
    return {
        "id": str(i.pk),
        "participant_id": str(i.participant_id),
        "participant": i.participant.full_name_source,
        "need": i.need,
        "need_label": NEED_NAMES[i.need],
        "title": i.title,
        "status": i.status,
        "status_label": STATUS_NAMES[i.status],
        "owner": _user_name(i.owner),
        "owner_id": i.owner_id,
        "due_date": i.due_date.isoformat() if i.due_date else None,
        "overdue": services.is_overdue(i, today),
        "follow_up_of_id": str(i.follow_up_of_id) if i.follow_up_of_id else None,
        "closed_at": i.closed_at.isoformat() if i.closed_at else None,
        "updated_at": i.updated_at.isoformat(),
    }


def _detail(i, user):
    today = timezone.localdate()
    return {
        **_summary(i, today),
        "detail": i.detail,
        "verification_source": i.verification_source,
        "verification_source_label": SOURCE_NAMES.get(i.verification_source, ""),
        "outcome_note": i.outcome_note,
        "created_by": _user_name(i.created_by),
        "created_at": i.created_at.isoformat(),
        "next_statuses": services.next_statuses(i),
        "follow_ups": [
            {"id": str(f.pk), "title": f.title, "status_label": STATUS_NAMES[f.status]}
            for f in i.follow_ups.all()
        ],
        "can": {
            "edit": has_permission(user, EDIT) and i.status in Intervention.LIVE,
            "reassign": has_permission(user, REASSIGN) and i.status in Intervention.LIVE,
            "follow_up": has_permission(user, EDIT),
        },
    }


def _base(user):
    return services.visible_interventions(user).select_related("participant", "owner", "created_by")


def _get(request, pk):
    try:
        return _base(request.user).prefetch_related("follow_ups").get(pk=pk)
    except Intervention.DoesNotExist:
        raise NotFound from None


class InterventionCreateSerializer(serializers.Serializer):
    participant_id = serializers.UUIDField(required=False)
    follow_up_of_id = serializers.UUIDField(required=False)
    need = serializers.ChoiceField(choices=[n for n, _ in Intervention.NEEDS])
    title = serializers.CharField(max_length=200)
    detail = serializers.CharField(required=False, allow_blank=True, max_length=4000, default="")
    owner_id = serializers.IntegerField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs.get("participant_id") and not attrs.get("follow_up_of_id"):
            raise serializers.ValidationError({"participant_id": ["Choose the youth."]})
        return attrs


class InterventionUpdateSerializer(serializers.Serializer):
    need = serializers.ChoiceField(choices=[n for n, _ in Intervention.NEEDS], required=False)
    title = serializers.CharField(max_length=200, required=False)
    detail = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    due_date = serializers.DateField(required=False, allow_null=True)


class InterventionMoveSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=[s for s, _ in Intervention.STATUSES])
    verification_source = serializers.ChoiceField(
        choices=[s for s, _ in Intervention.SOURCES], required=False, default=""
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class InterventionAssignSerializer(serializers.Serializer):
    owner_id = serializers.IntegerField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class InterventionListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "POST": EDIT}

    @extend_schema(
        operation_id="interventions_list",
        parameters=[
            OpenApiParameter(n, str)
            for n in (
                "q",
                "status",
                "need",
                "mine",
                "overdue",
                "participant",
                "offset",
                "page_size",
            )
        ],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        today = timezone.localdate()
        qs = _base(request.user)
        if q := g.get("q", "").strip():
            qs = qs.filter(Q(title__icontains=q) | Q(participant__full_name_source__icontains=q))
        if g.get("status") == "live":
            qs = qs.filter(status__in=Intervention.LIVE)
        elif g.get("status") in STATUS_NAMES:
            qs = qs.filter(status=g["status"])
        if g.get("need") in NEED_NAMES:
            qs = qs.filter(need=g["need"])
        if g.get("mine") == "1":
            qs = qs.filter(owner=request.user)
        if g.get("overdue") == "1":
            qs = qs.filter(status__in=Intervention.LIVE, due_date__lt=today)
        try:
            if g.get("participant"):
                qs = qs.filter(participant_id=uuid.UUID(g["participant"]))
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            raise serializers.ValidationError({"filter": ["Invalid filter value."]}) from None
        size = page_size_of(g)
        return Response(
            {
                "total": qs.count(),
                "page_size": size,
                "results": [_summary(i, today) for i in qs[offset : offset + size]],
            }
        )

    @extend_schema(request=InterventionCreateSerializer, responses={201: dict, 409: dict})
    def post(self, request):
        s = InterventionCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            i = services.create_intervention(
                actor=request.user, participant_id=d.get("participant_id"), need=d["need"],
                title=d["title"], detail=d["detail"], owner_id=d.get("owner_id"),
                due_date=d.get("due_date"), follow_up_of_id=d.get("follow_up_of_id"),
            )  # fmt: skip
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_detail(_get(request, i.pk), request.user), status=status.HTTP_201_CREATED)


class InterventionDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "PATCH": EDIT}

    @extend_schema(operation_id="interventions_detail", responses={200: dict})
    def get(self, request, pk):
        return Response(_detail(_get(request, pk), request.user))

    @extend_schema(
        operation_id="interventions_update",
        request=InterventionUpdateSerializer,
        responses={200: dict, 409: dict},
    )
    def patch(self, request, pk):
        i = _get(request, pk)
        s = InterventionUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        try:
            services.update_intervention(actor=request.user, intervention=i, **s.validated_data)
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_detail(_get(request, pk), request.user))


class InterventionMoveView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT}

    @extend_schema(
        operation_id="interventions_move", request=InterventionMoveSerializer,
        responses={200: dict, 409: dict},
    )  # fmt: skip
    def post(self, request, pk):
        i = _get(request, pk)
        s = InterventionMoveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            services.move_intervention(
                actor=request.user, intervention=i, to=d["to"],
                verification_source=d["verification_source"], note=d["note"],
            )  # fmt: skip
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_detail(_get(request, pk), request.user))


class InterventionAssignView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": REASSIGN}

    @extend_schema(
        operation_id="interventions_assign", request=InterventionAssignSerializer,
        responses={200: dict, 409: dict},
    )  # fmt: skip
    def post(self, request, pk):
        i = _get(request, pk)
        s = InterventionAssignSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.assign_intervention(
                actor=request.user, intervention=i, owner_id=s.validated_data["owner_id"],
                note=s.validated_data["note"],
            )  # fmt: skip
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_detail(_get(request, pk), request.user))


class InterventionHistoryView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(
        operation_id="interventions_history", responses={200: dict(type="array", items={})}
    )
    def get(self, request, pk):
        return Response(audit.history("intervention", _get(request, pk).pk))


class InterventionOptionsView(APIView):
    """The controlled lists the forms use: kinds of support and verification sources."""

    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="interventions_options", responses={200: dict})
    def get(self, request):
        return Response(
            {
                "needs": [{"value": v, "label": label} for v, label in Intervention.NEEDS],
                "sources": [{"value": v, "label": label} for v, label in Intervention.SOURCES],
                "statuses": [{"value": v, "label": label} for v, label in Intervention.STATUSES],
            }
        )
