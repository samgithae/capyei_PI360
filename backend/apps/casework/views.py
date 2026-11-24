"""Case management API (T-064 work queue, T-065 placements).

referrals.view reads the work queue; placements.view reads episodes and placements.edit enters,
corrects, ends and verifies them. A placement whose youth is outside the caller's scope gives
404."""

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
OPERATIONAL = [c for c, _ in services.placements.Placement.OPERATIONAL_STATUSES]


class SelfEmploymentFields(serializers.Serializer):
    """D-080 / B27 (NEW-071): only for the self-employment pathway; the service refuses them on
    any other. monthly_income needs the restricted economic-data grant."""

    business_activity = serializers.CharField(required=False, allow_blank=True, max_length=200)
    operational_status = serializers.ChoiceField(
        choices=OPERATIONAL, required=False, allow_blank=True
    )
    business_evidence = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    monthly_income = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True
    )


class WorkTermsFields(serializers.Serializer):
    """NEW-035 (B25, A3): the employment type, and the salary or its band. The salary and band
    need the restricted economic-data grant; the service refuses them on self-employment."""

    employment_type_id = serializers.UUIDField(required=False, allow_null=True)
    salary_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    salary_band_id = serializers.UUIDField(required=False, allow_null=True)


class PlacementFields(SelfEmploymentFields, WorkTermsFields):
    pass


FOLLOWUP_KINDS = [c for c, _ in services.placements.FollowUpStep.KINDS]
FOLLOWUP_METHODS = [c for c, _ in services.placements.FollowUpAttempt.METHODS]
FOLLOWUP_OUTCOMES = [c for c, _ in services.placements.FollowUp.OUTCOMES]
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


class PlacementCreateSerializer(PlacementFields):
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


class PlacementUpdateSerializer(PlacementFields):
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


class PlacementChangeEmployerSerializer(PlacementFields):
    """End the running placement and start the next one (D-081)."""

    end_date = serializers.DateField()
    start_date = serializers.DateField()
    pathway = serializers.ChoiceField(choices=PATHWAYS)
    employer_id = serializers.UUIDField(required=False, allow_null=True)
    employer_name_source = serializers.CharField(
        required=False, allow_blank=True, max_length=255, default=""
    )
    designation = serializers.CharField(
        required=False, allow_blank=True, max_length=255, default=""
    )
    benefits = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


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
            filters = services.placement_filters(g)
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            raise serializers.ValidationError({"filter": ["Invalid filter value."]}) from None
        size = page_size_of(g)
        total, rows = services.list_placements(request.user, offset=offset, size=size, **filters)
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
                # PROVISIONAL list (NEW-071): CAP-YEI has not given one yet.
                "operational_statuses": [
                    {"value": v, "label": label} for v, label in P.OPERATIONAL_STATUSES
                ],
                "operational_statuses_provisional": True,
                "can_record_income": services.can_see_income(request.user),
                # NEW-035. Bands are listed only to those who may record a salary.
                "employment_types": services.placements.outcome_list("employment-types"),
                "salary_bands": (
                    services.placements.outcome_list("salary-bands")
                    if services.can_see_income(request.user)
                    else []
                ),
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


class PlacementChangeEmployerView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": PLACEMENTS_EDIT}

    @extend_schema(
        operation_id="placements_change_employer", request=PlacementChangeEmployerSerializer,
        responses={201: dict, 409: dict},
    )  # fmt: skip
    def post(self, request, pk):
        p = _get(request, pk)
        s = PlacementChangeEmployerSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            new = services.change_employer(actor=request.user, placement=p, **s.validated_data)
        except services.Violation as exc:
            return _violation(exc)
        return Response(_detail(request, _get(request, new.pk)), status=status.HTTP_201_CREATED)


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


class NewJobSerializer(PlacementFields):
    """The work a youth moved to, found at a follow-up (NEW-034)."""

    pathway = serializers.ChoiceField(choices=PATHWAYS, required=False)
    start_date = serializers.DateField()
    employer_id = serializers.UUIDField(required=False, allow_null=True)
    employer_name_source = serializers.CharField(required=False, allow_blank=True, max_length=255)
    designation = serializers.CharField(required=False, allow_blank=True, max_length=255)
    benefits = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class FollowUpCompleteSerializer(serializers.Serializer):
    """Send ``outcome`` (NEW-034). ``still_employed`` alone is the form before it, still accepted:
    it records the answer without changing the placements."""

    outcome = serializers.ChoiceField(
        choices=FOLLOWUP_OUTCOMES, required=False, allow_blank=True, default=""
    )
    still_employed = serializers.BooleanField(required=False, allow_null=True, default=None)
    evidence_source = serializers.ChoiceField(choices=SOURCES)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
    leaving_reason_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    left_on = serializers.DateField(required=False, allow_null=True, default=None)
    observations = serializers.CharField(
        required=False, allow_blank=True, max_length=2000, default=""
    )
    new_job = NewJobSerializer(required=False, allow_null=True, default=None)


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
            filters = services.followup_filters(request.user, g)
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            raise serializers.ValidationError({"filter": ["Invalid filter value."]}) from None
        size = page_size_of(g)
        total, rows = services.list_followups(request.user, offset=offset, size=size, **filters)
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
                # NEW-034: outcomes and reasons for leaving; the new-work part of the form uses
                # the placement options (pathways, employment types, salary bands).
                **services.placements.followup_outcome_lists(),
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


# --- NEW-077: resolving two running placements on a pending youth merge ----------------------


class MergeResolveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["end", "same"])
    placement_id = serializers.UUIDField()
    keep_id = serializers.UUIDField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    exit_reason = serializers.CharField(max_length=200, required=False, allow_blank=True)
    reason = serializers.CharField(max_length=500)


class MergeResolveView(APIView):
    """An authorised officer resolves the running-placement conflict that holds a merge: they
    need the merge permission and the right to edit placements. The choice is kept with the
    merge (who, when, why, what)."""

    permission_classes = [HasPermission]
    required_permission = {"POST": "duplicates.merge"}

    @extend_schema(request=MergeResolveSerializer, responses={201: dict, 403: dict, 409: dict})
    def post(self, request, pk):
        from apps.participants import services as participants

        from . import merge_checks

        if not has_permission(request.user, PLACEMENTS_EDIT):
            return Response(
                {"errors": [{"field": "non_field_errors", "code": "forbidden",
                             "message": "You need the right to edit placements."}]},
                status=status.HTTP_403_FORBIDDEN,
            )  # fmt: skip
        cand = participants.get_candidate(pk)
        if cand is None:
            raise NotFound()
        s = MergeResolveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            row = merge_checks.resolve_placements(
                actor=request.user, candidate=cand, **s.validated_data
            )
        except merge_checks.ResolutionError as exc:
            return Response(
                {"errors": [{"field": exc.field, "message": exc.message, "code": "merge_rule"}]},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {"id": str(row.pk), "conflict": row.conflict, "action": row.action},
            status=status.HTTP_201_CREATED,
        )
