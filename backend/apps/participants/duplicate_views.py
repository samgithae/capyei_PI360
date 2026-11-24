"""Steward duplicate queue API (T-041): review candidate pairs, merge, dismiss, undo."""

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission, has_permission

from . import duplicates, services
from .models import DuplicateCandidate, MergeResolution, ParticipantMerge

REVIEW, MERGE, CONTACT = "duplicates.review", "duplicates.merge", "participants.view_contact"


def _person(p, with_contacts):
    enrollments = list(p.enrollments.select_related("project", "cohort_course__cohort"))
    out = {
        "id": str(p.pk),
        "name": p.full_name_source,
        "gender": p.gender,
        "age": p.age_at_source,
        "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
        "status": p.status,
        "county": p.origin_county.name if p.origin_county_id else "",
        "projects": sorted({e.project.name for e in enrollments}),
        "cohorts": sorted({e.cohort_course.cohort.name for e in enrollments}),
        "enrollment_numbers": sorted(
            e.source_enrollment_no for e in enrollments if e.source_enrollment_no
        ),
    }
    if with_contacts:
        out["phones"] = [c.value for c in p.contacts.all() if c.kind == "phone"]
    return out


def _resolution(r):
    return {
        "id": str(r.pk),
        "conflict": r.conflict,
        "action": r.action,
        "detail": r.detail,
        "reason": r.reason,
        "decided_by": r.decided_by.get_username() if r.decided_by_id else "",
        "decided_at": r.decided_at.isoformat(),
    }


def _candidate(c, with_contacts):
    out = {
        "id": str(c.pk),
        "score": c.score,
        "reasons": [{"code": r, "text": duplicates.RULES.get(r, (0, r))[1]} for r in c.reasons],
        "status": c.status,
        "note": c.note,
        "a": _person(c.participant_a, with_contacts),
        "b": _person(c.participant_b, with_contacts),
    }
    if c.status == DuplicateCandidate.PENDING:
        plan = c.plan
        out["pending"] = {
            "survivor": plan.get("survivor"),
            "reason": plan.get("reason", ""),
            "saved_at": plan.get("saved_at"),
            "resolutions": [_resolution(r) for r in c.resolutions.select_related("decided_by")],
        }
    return out


def _merge_out(m):
    resolutions = (
        MergeResolution.objects.filter(candidate_id=m.candidate_id).select_related("decided_by")
        if m.candidate_id
        else []
    )
    return {
        "id": str(m.pk),
        "survivor": {"id": str(m.survivor_id), "name": m.survivor.full_name_source},
        "absorbed": {"id": str(m.absorbed_id), "name": m.absorbed.full_name_source},
        "reason": m.reason,
        "created_at": m.created_at.isoformat(),
        "created_by": m.created_by.get_username() if m.created_by_id else "",
        "undone_at": m.undone_at.isoformat() if m.undone_at else None,
        "undo_reason": m.undo_reason,
        "resolutions": [_resolution(r) for r in resolutions],
    }


def _conflict(exc):
    return Response(
        {"errors": [{"field": exc.field, "message": exc.message, "code": "duplicate_rule"}]},
        status=status.HTTP_409_CONFLICT,
    )


class MergeSerializer(serializers.Serializer):
    survivor = serializers.UUIDField()
    fields = serializers.DictField(child=serializers.CharField(), required=False)
    reason = serializers.CharField(max_length=500)


class DuplicateReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=True, default="")


class DuplicateListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": REVIEW}

    @extend_schema(responses={200: dict})
    def get(self, request):
        state = request.query_params.get("status", DuplicateCandidate.OPEN)
        qs = (
            DuplicateCandidate.objects.filter(status=state)
            .select_related("participant_a__origin_county", "participant_b__origin_county")
            .prefetch_related("participant_a__contacts", "participant_b__contacts")
            .order_by("-score", "created_at")[:200]
        )
        contacts = has_permission(request.user, CONTACT)
        return Response({"results": [_candidate(c, contacts) for c in qs]})


class DuplicateScanView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": REVIEW}

    @extend_schema(request=None, responses={200: dict})
    def post(self, request):
        return Response(services.scan(actor=request.user))


class DuplicateDismissView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": REVIEW}

    @extend_schema(request=DuplicateReasonSerializer, responses={200: dict, 409: dict})
    def post(self, request, pk):
        s = DuplicateReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        cand = get_object_or_404(DuplicateCandidate, pk=pk)
        try:
            services.dismiss(actor=request.user, candidate=cand, note=s.validated_data["reason"])
        except services.DuplicateFailure as exc:
            return _conflict(exc)
        return Response({"id": str(pk), "status": "dismissed"})


class DuplicateReviewView(APIView):
    """What a merge into the chosen survivor would do: values filled automatically, real
    conflicts to choose, and critical conflicts that hold the merge (NEW-077)."""

    permission_classes = [HasPermission]
    required_permission = {"GET": MERGE}

    @extend_schema(
        parameters=[OpenApiParameter("survivor", str, required=True)],
        responses={200: dict, 409: dict},
    )
    def get(self, request, pk):
        cand = get_object_or_404(DuplicateCandidate, pk=pk)
        try:
            return Response(
                services.review(candidate=cand, survivor_id=request.query_params.get("survivor"))
            )
        except (services.DuplicateFailure, ValueError, ValidationError) as exc:
            return _conflict(
                exc if isinstance(exc, services.DuplicateFailure)
                else services.DuplicateFailure("Choose the survivor.", "survivor")
            )  # fmt: skip


class DuplicateMergeView(APIView):
    """Merge, or, while a critical conflict remains, save the merge as pending resolution
    (202, with the conflicts). Nothing moves until it is completed."""

    permission_classes = [HasPermission]
    required_permission = {"POST": MERGE}

    @extend_schema(request=MergeSerializer, responses={200: dict, 202: dict, 409: dict})
    def post(self, request, pk):
        s = MergeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        cand = get_object_or_404(DuplicateCandidate, pk=pk)
        try:
            result = services.merge(
                actor=request.user,
                candidate=cand,
                survivor_id=s.validated_data["survivor"],
                fields=s.validated_data.get("fields"),
                reason=s.validated_data["reason"],
            )
        except services.DuplicateFailure as exc:
            return _conflict(exc)
        if isinstance(result, DuplicateCandidate):
            return Response(
                {"id": str(result.pk), "status": result.status, "conflicts": result.conflicts},
                status=status.HTTP_202_ACCEPTED,
            )
        return Response(_merge_out(result))


class DuplicateCompleteView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": MERGE}

    @extend_schema(request=None, responses={200: dict, 409: dict})
    def post(self, request, pk):
        cand = get_object_or_404(DuplicateCandidate, pk=pk)
        try:
            record = services.complete(actor=request.user, candidate=cand)
        except services.DuplicateFailure as exc:
            return _conflict(exc)
        return Response(_merge_out(record))


class MergeListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": REVIEW}

    @extend_schema(responses={200: dict})
    def get(self, request):
        qs = ParticipantMerge.objects.select_related("survivor", "absorbed", "created_by")[:100]
        return Response({"results": [_merge_out(m) for m in qs]})


class MergeUndoView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": MERGE}

    @extend_schema(request=DuplicateReasonSerializer, responses={200: dict, 409: dict})
    def post(self, request, pk):
        s = DuplicateReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        record = get_object_or_404(ParticipantMerge, pk=pk)
        try:
            services.unmerge(
                actor=request.user, merge_record=record, reason=s.validated_data["reason"]
            )
        except services.DuplicateFailure as exc:
            return _conflict(exc)
        record.refresh_from_db()
        return Response(_merge_out(record))
