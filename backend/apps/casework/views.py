"""Case management API (T-064 work queue, T-065 placements).

referrals.view reads the work queue; placements.view reads episodes and placements.edit enters,
corrects, ends and verifies them. A placement whose youth is outside the caller's scope gives
404."""

import uuid

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission, has_permission
from apps.api.pagination import page_size_of

from . import services

PLACEMENTS_VIEW, PLACEMENTS_EDIT = "placements.view", "placements.edit"
REASSIGN = "caseload.reassign"
CONFIG_VIEW, CONFIG_MANAGE = "config.view", "config.manage"
QUEUE_VIEW = "referrals.view"
PATHWAYS = [c for c, _ in services.placements.Placement.PATHWAYS]
SOURCES = [c for c, _ in services.placements.Placement.SOURCES]
FOLLOWUP_KINDS = [c for c, _ in services.placements.FollowUpStep.KINDS]
FOLLOWUP_METHODS = [c for c, _ in services.placements.FollowUpAttempt.METHODS]
FOLLOWUP_STATES = ("open", "overdue", "due_soon", "done", "closed", "all")


def _violation(exc):
    return Response(
        {"errors": [{"field": exc.field, "message": exc.message, "code": exc.code}]},
        status=status.HTTP_409_CONFLICT,
    )


def _get(request, pk):
    try:
        return services.get_placement(request.user, pk)
    except services.NotFound:
        raise NotFound from None


def _detail(request, p):
    return services.detail(request.user, p, can_edit=has_permission(request.user, PLACEMENTS_EDIT))


class PlacementCreateSerializer(serializers.Serializer):
    participant_id = serializers.UUIDField()
    enrollment_id = serializers.UUIDField(required=False)
    pathway = serializers.ChoiceField(choices=PATHWAYS)
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True)
    exit_reason = serializers.CharField(
        required=False, allow_blank=True, max_length=200, default=""
    )
    employer_id = serializers.UUIDField(required=False, allow_null=True)
    employer_name_source = serializers.CharField(
        required=False, allow_blank=True, max_length=255, default=""
    )
    designation = serializers.CharField(
        required=False, allow_blank=True, max_length=255, default=""
    )
    benefits = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class PlacementUpdateSerializer(serializers.Serializer):
    pathway = serializers.ChoiceField(choices=PATHWAYS, required=False)
    start_date = serializers.DateField(required=False)
    employer_id = serializers.UUIDField(required=False, allow_null=True)
    employer_name_source = serializers.CharField(required=False, allow_blank=True, max_length=255)
    designation = serializers.CharField(required=False, allow_blank=True, max_length=255)
    benefits = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class PlacementEndSerializer(serializers.Serializer):
    end_date = serializers.DateField()
    exit_reason = serializers.CharField(
        required=False, allow_blank=True, max_length=200, default=""
    )


class PlacementVerifySerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=SOURCES)


class QueueView(APIView):
    """The officer's work queue: interventions (overdue first), referrals waiting, flags."""

    permission_classes = [HasPermission]
    required_permission = {"GET": QUEUE_VIEW}

    @extend_schema(
        operation_id="cases_queue",
        parameters=[OpenApiParameter("mine", str)],
        responses={200: dict},
    )
    def get(self, request):
        return Response(
            services.queue(request.user, mine=request.query_params.get("mine", "1") != "0")
        )


class PlacementListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PLACEMENTS_VIEW, "POST": PLACEMENTS_EDIT}

    @extend_schema(
        operation_id="placements_list",
        parameters=[
            OpenApiParameter(n, str)
            for n in ("q", "pathway", "state", "employer", "participant", "offset", "page_size")
        ],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        try:
            employer = uuid.UUID(g["employer"]) if g.get("employer") else None
            participant = uuid.UUID(g["participant"]) if g.get("participant") else None
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            raise serializers.ValidationError({"filter": ["Invalid filter value."]}) from None
        size = page_size_of(g)
        total, rows = services.list_placements(
            request.user,
            pathway=g.get("pathway") if g.get("pathway") in PATHWAYS else "",
            state=g.get("state") if g.get("state") in ("current", "ended", "unverified") else "",
            employer_id=employer, q=g.get("q", "").strip(), participant_id=participant,
            offset=offset, size=size,
        )  # fmt: skip
        return Response({"total": total, "page_size": size, "results": rows})

    @extend_schema(request=PlacementCreateSerializer, responses={201: dict, 409: dict})
    def post(self, request):
        s = PlacementCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        try:
            p = services.create_placement(actor=request.user, **d)
        except services.Violation as exc:
            return _violation(exc)
        return Response(_detail(request, _get(request, p.pk)), status=status.HTTP_201_CREATED)


class PlacementSummaryView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PLACEMENTS_VIEW}

    @extend_schema(operation_id="placements_summary", responses={200: dict})
    def get(self, request):
        return Response(services.summary(request.user))


class PlacementOptionsView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PLACEMENTS_VIEW}

    @extend_schema(operation_id="placements_options", responses={200: dict})
    def get(self, request):
        P = services.placements.Placement
        return Response(
            {
                "pathways": [{"value": v, "label": label} for v, label in P.PATHWAYS],
                "sources": [{"value": v, "label": label} for v, label in P.SOURCES],
            }
        )


class PlacementDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PLACEMENTS_VIEW, "PATCH": PLACEMENTS_EDIT}

    @extend_schema(operation_id="placements_detail", responses={200: dict})
    def get(self, request, pk):
        return Response(_detail(request, _get(request, pk)))

    @extend_schema(
        operation_id="placements_update",
        request=PlacementUpdateSerializer,
        responses={200: dict, 409: dict},
    )
    def patch(self, request, pk):
        p = _get(request, pk)
        s = PlacementUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        try:
            services.update_placement(actor=request.user, placement=p, **s.validated_data)
        except services.Violation as exc:
            return _violation(exc)
        return Response(_detail(request, _get(request, pk)))


class PlacementEndView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": PLACEMENTS_EDIT}

    @extend_schema(
        operation_id="placements_end", request=PlacementEndSerializer,
        responses={200: dict, 409: dict},
    )  # fmt: skip
    def post(self, request, pk):
        p = _get(request, pk)
        s = PlacementEndSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.end_placement(actor=request.user, placement=p, **s.validated_data)
        except services.Violation as exc:
            return _violation(exc)
        return Response(_detail(request, _get(request, pk)))


class PlacementVerifyView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": PLACEMENTS_EDIT}

    @extend_schema(
        operation_id="placements_verify", request=PlacementVerifySerializer,
        responses={200: dict, 409: dict},
    )  # fmt: skip
    def post(self, request, pk):
        p = _get(request, pk)
        s = PlacementVerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.verify_placement(
                actor=request.user, placement=p, source=s.validated_data["source"]
            )
        except services.Violation as exc:
            return _violation(exc)
        return Response(_detail(request, _get(request, pk)))


class PlacementHistoryView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PLACEMENTS_VIEW}

    @extend_schema(operation_id="placements_history", responses={200: dict(type="array", items={})})
    def get(self, request, pk):
        return Response(services.history(_get(request, pk)))


# --- follow-ups (T-066) --------------------------------------------------------------------------


def _get_followup(request, pk):
    try:
        return services.get_followup(request.user, pk)
    except services.NotFound:
        raise NotFound from None


def _followup_detail(request, f):
    return services.followup_detail(
        request.user, f,
        can_edit=has_permission(request.user, PLACEMENTS_EDIT),
        can_assign=has_permission(request.user, REASSIGN),
    )  # fmt: skip


class FollowUpAttemptSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=FOLLOWUP_METHODS)
    reached = serializers.BooleanField()
    made_on = serializers.DateField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
    next_action = serializers.CharField(
        required=False, allow_blank=True, max_length=200, default=""
    )
    next_action_date = serializers.DateField(required=False, allow_null=True, default=None)


class FollowUpCompleteSerializer(serializers.Serializer):
    still_employed = serializers.BooleanField()
    evidence_source = serializers.ChoiceField(choices=SOURCES)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class FollowUpUnreachableSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class FollowUpCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class FollowUpAssignSerializer(serializers.Serializer):
    owner_id = serializers.IntegerField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class FollowUpStepCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=FOLLOWUP_KINDS)
    label = serializers.CharField(max_length=60)
    offset_days = serializers.IntegerField(min_value=1, max_value=732)
    active = serializers.BooleanField(required=False, default=True)


class FollowUpStepUpdateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=FOLLOWUP_KINDS, required=False)
    label = serializers.CharField(max_length=60, required=False)
    offset_days = serializers.IntegerField(min_value=1, max_value=732, required=False)
    active = serializers.BooleanField(required=False)


class FollowUpListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PLACEMENTS_VIEW}

    @extend_schema(
        operation_id="followups_list",
        parameters=[
            OpenApiParameter(n, str)
            for n in ("q", "state", "kind", "mine", "participant", "placement", "offset",
                      "page_size")
        ],
        responses={200: dict},
    )  # fmt: skip
    def get(self, request):
        g = request.query_params
        try:
            participant = uuid.UUID(g["participant"]) if g.get("participant") else None
            placement = uuid.UUID(g["placement"]) if g.get("placement") else None
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            raise serializers.ValidationError({"filter": ["Invalid filter value."]}) from None
        size = page_size_of(g)
        total, rows = services.list_followups(
            request.user,
            state=g.get("state") if g.get("state") in FOLLOWUP_STATES else "open",
            kind=g.get("kind") if g.get("kind") in FOLLOWUP_KINDS else "",
            mine=g.get("mine") == "1", q=g.get("q", "").strip(), participant_id=participant,
            placement_id=placement, offset=offset, size=size,
        )  # fmt: skip
        return Response({"total": total, "page_size": size, "results": rows})


class FollowUpSummaryView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PLACEMENTS_VIEW}

    @extend_schema(
        operation_id="followups_summary",
        parameters=[OpenApiParameter("mine", str)],
        responses={200: dict},
    )
    def get(self, request):
        return Response(
            services.followup_summary(request.user, mine=request.query_params.get("mine") == "1")
        )


class FollowUpOptionsView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PLACEMENTS_VIEW}

    @extend_schema(operation_id="followups_options", responses={200: dict})
    def get(self, request):
        return Response(
            {
                "methods": [
                    {"value": v, "label": label}
                    for v, label in services.placements.FollowUpAttempt.METHODS
                ],
                "sources": [
                    {"value": v, "label": label}
                    for v, label in services.placements.Placement.SOURCES
                ],
            }
        )


class FollowUpDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PLACEMENTS_VIEW}

    @extend_schema(operation_id="followups_detail", responses={200: dict})
    def get(self, request, pk):
        return Response(_followup_detail(request, _get_followup(request, pk)))


class FollowUpHistoryView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PLACEMENTS_VIEW}

    @extend_schema(operation_id="followups_history", responses={200: dict(type="array", items={})})
    def get(self, request, pk):
        return Response(services.followup_history(_get_followup(request, pk)))


def _followup_action(request, pk, serializer_class, call, **extra):
    """Run one change on a follow-up and return its refreshed detail (409 on a broken rule)."""
    f = _get_followup(request, pk)
    s = serializer_class(data=request.data)
    s.is_valid(raise_exception=True)
    try:
        call(actor=request.user, followup=f, **{**s.validated_data, **extra})
    except services.Violation as exc:
        return _violation(exc)
    return Response(_followup_detail(request, _get_followup(request, pk)))


class FollowUpAttemptView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": PLACEMENTS_EDIT}

    @extend_schema(
        operation_id="followups_attempt", request=FollowUpAttemptSerializer,
        responses={200: dict, 409: dict},
    )  # fmt: skip
    def post(self, request, pk):
        return _followup_action(request, pk, FollowUpAttemptSerializer, services.log_attempt)


class FollowUpCompleteView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": PLACEMENTS_EDIT}

    @extend_schema(
        operation_id="followups_complete", request=FollowUpCompleteSerializer,
        responses={200: dict, 409: dict},
    )  # fmt: skip
    def post(self, request, pk):
        return _followup_action(request, pk, FollowUpCompleteSerializer, services.complete_followup)


class FollowUpUnreachableView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": PLACEMENTS_EDIT}

    @extend_schema(
        operation_id="followups_unreachable", request=FollowUpUnreachableSerializer,
        responses={200: dict, 409: dict},
    )  # fmt: skip
    def post(self, request, pk):
        return _followup_action(
            request, pk, FollowUpUnreachableSerializer, services.unreachable_followup
        )


class FollowUpCancelView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": PLACEMENTS_EDIT}

    @extend_schema(
        operation_id="followups_cancel", request=FollowUpCancelSerializer,
        responses={200: dict, 409: dict},
    )  # fmt: skip
    def post(self, request, pk):
        return _followup_action(request, pk, FollowUpCancelSerializer, services.cancel_followup)


class FollowUpAssignView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": REASSIGN}

    @extend_schema(
        operation_id="followups_assign", request=FollowUpAssignSerializer,
        responses={200: dict, 409: dict},
    )  # fmt: skip
    def post(self, request, pk):
        return _followup_action(request, pk, FollowUpAssignSerializer, services.assign_followup)


class FollowUpStepListView(APIView):
    """The schedule the check-ins are generated from. A change affects new placements only."""

    permission_classes = [HasPermission]
    required_permission = {"GET": CONFIG_VIEW, "POST": CONFIG_MANAGE}

    @extend_schema(operation_id="followup_steps_list", responses={200: dict})
    def get(self, request):
        return Response({"results": services.schedule_steps()})

    @extend_schema(
        operation_id="followup_steps_create", request=FollowUpStepCreateSerializer,
        responses={201: dict, 409: dict},
    )  # fmt: skip
    def post(self, request):
        s = FollowUpStepCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.create_schedule_step(actor=request.user, **s.validated_data)
        except services.Violation as exc:
            return _violation(exc)
        return Response({"results": services.schedule_steps()}, status=status.HTTP_201_CREATED)


class FollowUpStepDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"PATCH": CONFIG_MANAGE}

    @extend_schema(
        operation_id="followup_steps_update", request=FollowUpStepUpdateSerializer,
        responses={200: dict, 409: dict},
    )  # fmt: skip
    def patch(self, request, pk):
        s = FollowUpStepUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        try:
            services.update_schedule_step(actor=request.user, step_id=pk, **s.validated_data)
        except services.Violation as exc:
            return _violation(exc)
        return Response({"results": services.schedule_steps()})
