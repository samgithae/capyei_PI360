"""Referral API (T-046). referrals.view reads, referrals.edit works referrals, reopening a
closed referral needs referrals.approve, and reassigning needs caseload.reassign.

A referral outside the caller's scope (its youth is not visible to them) gives 404."""

import uuid

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission, has_permission
from apps.api.pagination import page_size_of
from apps.audit import services as audit
from apps.configuration import services as configuration

from . import services
from .models import Referral

VIEW, EDIT, APPROVE, REASSIGN = (
    "referrals.view", "referrals.edit", "referrals.approve", "caseload.reassign"
)  # fmt: skip
STAGE_NAMES = dict(Referral.STAGES)


def _violation(exc):
    return Response(
        {"errors": [{"field": exc.field, "message": exc.message, "code": exc.code}]},
        status=status.HTTP_409_CONFLICT,
    )


def _user_name(u):
    return (u.get_full_name() or u.get_username()) if u else ""


def _summary(r):
    return {
        "id": str(r.pk),
        "participant_id": str(r.participant_id),
        "participant": r.participant.full_name_source,
        "opportunity_id": str(r.opportunity_id),
        "opportunity": r.opportunity.title,
        "employer": r.opportunity.employer.name,
        "origin": r.origin,
        "stage": r.stage,
        "stage_label": STAGE_NAMES[r.stage],
        "reason": r.reason.name if r.reason_id else "",
        "assigned_to": _user_name(r.assigned_to),
        "assigned_to_id": r.assigned_to_id,
        "referred_at": r.referred_at.isoformat() if r.referred_at else None,
        "closed_at": r.closed_at.isoformat() if r.closed_at else None,
        "updated_at": r.updated_at.isoformat(),
    }


def _detail(r, user):
    return {
        **_summary(r),
        "reason_id": str(r.reason_id) if r.reason_id else None,
        "reason_note": r.reason_note,
        "created_by": _user_name(r.created_by),
        "created_at": r.created_at.isoformat(),
        "next_stages": services.next_stages(r),
        "unsuccessful": sorted(Referral.UNSUCCESSFUL),
        "history": services.stage_history(r),
        "can": {
            "edit": has_permission(user, EDIT),
            "reopen": has_permission(user, APPROVE),
            "reassign": has_permission(user, REASSIGN),
        },
    }


def _base(user):
    return services.visible(user).select_related(
        "participant", "opportunity__employer", "reason", "assigned_to", "created_by"
    )


def _get(request, pk):
    try:
        return _base(request.user).get(pk=pk)
    except Referral.DoesNotExist:
        raise NotFound from None


class ReferralCreateSerializer(serializers.Serializer):
    participant_id = serializers.UUIDField()
    opportunity_id = serializers.UUIDField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    submit = serializers.BooleanField(required=False, default=True)


class ReferralMoveSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=[s for s, _ in Referral.STAGES])
    reason_id = serializers.UUIDField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class ReferralAssignSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class ReferralListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "POST": EDIT}

    @extend_schema(
        operation_id="referrals_list",
        parameters=[
            OpenApiParameter(n, str)
            for n in ("q", "stage", "participant", "opportunity", "mine", "offset", "page_size")
        ],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        qs = _base(request.user)
        if q := g.get("q", "").strip():
            qs = qs.filter(
                Q(participant__full_name_source__icontains=q)
                | Q(opportunity__title__icontains=q)
                | Q(opportunity__employer__name__icontains=q)
            )
        if g.get("stage") == "active":
            qs = qs.filter(stage__in=Referral.ACTIVE)
        elif g.get("stage") in STAGE_NAMES:
            qs = qs.filter(stage=g["stage"])
        if g.get("mine") == "1":
            qs = qs.filter(assigned_to=request.user)
        try:
            if g.get("participant"):
                qs = qs.filter(participant_id=uuid.UUID(g["participant"]))
            if g.get("opportunity"):
                qs = qs.filter(opportunity_id=uuid.UUID(g["opportunity"]))
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            raise serializers.ValidationError({"filter": ["Invalid filter value."]}) from None
        size = page_size_of(g)
        return Response(
            {
                "total": qs.count(),
                "page_size": size,
                "results": [_summary(r) for r in qs[offset : offset + size]],
            }
        )

    @extend_schema(request=ReferralCreateSerializer, responses={201: dict, 409: dict})
    def post(self, request):
        s = ReferralCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            r = services.create_referral(
                actor=request.user,
                participant_id=d["participant_id"],
                opportunity_id=d["opportunity_id"],
                note=d.get("note", ""),
                submit=d["submit"],
            )
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_detail(_get(request, r.pk), request.user), status=status.HTTP_201_CREATED)


class ReferralSummaryView(APIView):
    """Counts per stage for the list page's stat cards (scope applied)."""

    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="referrals_summary", responses={200: dict})
    def get(self, request):
        counts = services.counts_by_stage(request.user)
        return Response({s: counts.get(s, 0) for s in STAGE_NAMES})


class ReferralReasonsView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(
        operation_id="referrals_reasons",
        parameters=[OpenApiParameter("stage", str)],
        responses={200: dict(type="array", items={})},
    )
    def get(self, request):
        stage = request.query_params.get("stage")
        return Response(
            configuration.referral_reasons(stage if stage in Referral.UNSUCCESSFUL else None)
        )


class ReferralAssigneesView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": REASSIGN}

    @extend_schema(
        operation_id="referrals_assignees", responses={200: dict(type="array", items={})}
    )
    def get(self, request):
        return Response(services.assignees())


class ReferralDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="referrals_detail", responses={200: dict})
    def get(self, request, pk):
        return Response(_detail(_get(request, pk), request.user))


class ReferralTransitionView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT}

    @extend_schema(request=ReferralMoveSerializer, responses={200: dict, 409: dict})
    def post(self, request, pk):
        r = _get(request, pk)
        s = ReferralMoveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            services.transition(
                actor=request.user, referral=r, to=d["to"], reason_id=d.get("reason_id"),
                note=d["note"],
            )  # fmt: skip
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_detail(_get(request, pk), request.user))


class ReferralCorrectView(APIView):
    """Reopening a closed referral needs referrals.approve; other corrections referrals.edit.
    The route gate is referrals.view; the real check depends on the referral's stage."""

    permission_classes = [HasPermission]
    required_permission = {"POST": VIEW}

    @extend_schema(request=ReferralMoveSerializer, responses={200: dict, 409: dict})
    def post(self, request, pk):
        r = _get(request, pk)
        needed = APPROVE if r.stage == Referral.CLOSED else EDIT
        if not has_permission(request.user, needed):
            raise PermissionDenied(
                "Reopening a closed referral needs a manager's approval."
                if needed == APPROVE
                else "You cannot change referrals."
            )
        s = ReferralMoveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            services.correct(
                actor=request.user, referral=r, to=d["to"], reason_id=d.get("reason_id"),
                note=d["note"],
            )  # fmt: skip
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_detail(_get(request, pk), request.user))


class ReferralAssignView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": REASSIGN}

    @extend_schema(request=ReferralAssignSerializer, responses={200: dict, 409: dict})
    def post(self, request, pk):
        r = _get(request, pk)
        s = ReferralAssignSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.assign(
                actor=request.user, referral=r, user_id=s.validated_data["user_id"],
                note=s.validated_data["note"],
            )  # fmt: skip
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_detail(_get(request, pk), request.user))


class ReferralAuditView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="referrals_audit", responses={200: dict(type="array", items={})})
    def get(self, request, pk):
        return Response(audit.history("referral", _get(request, pk).pk))
