"""Data-quality screen API (T-074, SCR-32): rules and failing records, MIS corrections and the
reviewer's decisions on them."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission
from apps.api.pagination import page_size_of

from . import corrections, quality
from .models import Participant, ParticipantCorrection

REVIEW = "dataquality.review"


def _paging(g):
    try:
        offset = max(int(g.get("offset", 0)), 0)
    except ValueError:
        offset = 0
    return offset, page_size_of(g)


class QualitySummaryView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": REVIEW}

    @extend_schema(operation_id="dataquality_summary", responses={200: dict})
    def get(self, request):
        return Response(quality.summary(request.user))


class QualityRecordsView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": REVIEW}

    @extend_schema(
        operation_id="dataquality_records",
        parameters=[OpenApiParameter(n, str) for n in ("rule", "q", "offset", "page_size")],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        offset, size = _paging(g)
        try:
            data = quality.records(
                request.user,
                rule=g.get("rule") or None,
                q=g.get("q", ""),
                offset=offset,
                size=size,
            )
        except quality.UnknownRule as exc:
            raise serializers.ValidationError({"rule": [str(exc)]}) from None
        return Response(data)


class CorrectionListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": REVIEW}

    @extend_schema(
        operation_id="dataquality_corrections",
        parameters=[OpenApiParameter(n, str) for n in ("state", "q", "offset", "page_size")],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        offset, size = _paging(g)
        try:
            qs = corrections.filtered(request.user, g)
        except ValueError as exc:
            raise serializers.ValidationError({"state": [str(exc)]}) from None
        everyone = corrections.filtered(request.user, {"state": "all"})
        return Response(
            {
                "total": qs.count(),
                "page_size": size,
                "counts": {
                    "open": everyone.filter(state=ParticipantCorrection.OPEN).count(),
                    "conflict": everyone.filter(
                        state=ParticipantCorrection.OPEN, conflict_at__isnull=False
                    ).count(),
                },
                "results": [corrections.out(c) for c in qs[offset : offset + size]],
            }
        )


class ResolveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=corrections.ACTIONS)
    note = serializers.CharField(max_length=500, allow_blank=True, default="")


class CorrectionResolveView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": REVIEW}

    @extend_schema(
        operation_id="dataquality_correction_resolve",
        request=ResolveSerializer,
        responses={200: dict, 409: dict},
    )
    def post(self, request, pk):
        s = ResolveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        visible = Participant.objects.visible_to(request.user, archived=None)
        c = get_object_or_404(ParticipantCorrection, pk=pk, participant__in=visible)
        try:
            c = corrections.resolve(
                actor=request.user,
                correction=c,
                action=s.validated_data["action"],
                note=s.validated_data["note"],
            )
        except corrections.CorrectionError as exc:
            return Response(
                {"errors": [{"field": exc.field, "message": exc.message, "code": exc.code}]},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(corrections.out(c))
