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
QUEUE_VIEW = "referrals.view"
PATHWAYS = [c for c, _ in services.placements.Placement.PATHWAYS]
SOURCES = [c for c, _ in services.placements.Placement.SOURCES]


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
