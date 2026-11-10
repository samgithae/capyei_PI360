"""Participant API (T-058, T-043 core): directory, profile, edit. Every query is scoped to the
caller (SEC-06); records outside scope are 404. Contact details need participants.view_contact."""

import uuid

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission, has_permission
from apps.audit import services as audit
from apps.configuration import services as configuration

from .models import Participant

VIEW, EDIT, CONTACT = "participants.view", "participants.edit", "participants.view_contact"
PAGE = 50


def _visible(request):
    return Participant.objects.visible_to(request.user)


def _summary(p):
    enrollments = list(p.enrollments.all())
    return {
        "id": str(p.pk),
        "name": p.full_name_source,
        "gender": p.gender,
        "age": p.age_at_source,
        "status": p.status,
        "county": p.origin_county.name if p.origin_county_id else "",
        "programmes": sorted({e.programme.name for e in enrollments}),
        "cohorts": sorted({e.cohort_course.cohort.name for e in enrollments}),
    }


def _detail(p, user):
    out = _summary(p)
    out.update(
        given_name=p.given_name,
        family_name=p.family_name,
        other_names=p.other_names,
        age_basis_date=p.age_basis_date.isoformat() if p.age_basis_date else None,
        date_of_birth=p.date_of_birth.isoformat() if p.date_of_birth else None,
        enrollments=[
            {
                "id": str(e.pk),
                "programme": e.programme.name,
                "cohort": e.cohort_course.cohort.name,
                "course": e.cohort_course.course.name,
                "institution": e.institution.name,
                "enrollment_no": e.source_enrollment_no,
                "status": e.status,
                "enrolled_on": e.enrolled_on.isoformat() if e.enrolled_on else None,
                "completed_on": e.completed_on.isoformat() if e.completed_on else None,
            }
            for e in p.enrollments.select_related(
                "programme", "institution", "cohort_course__cohort", "cohort_course__course"
            )
        ],
        residences=[
            {
                "county": r.county.name if r.county_id else "",
                "sub_county": r.sub_county_source,
                "ward": r.ward_source,
                "current": r.valid_to is None,
            }
            for r in p.residences.all()
        ],
    )
    if has_permission(user, CONTACT):
        out["contacts"] = [
            {"kind": c.kind, "value": c.value, "primary": c.is_primary} for c in p.contacts.all()
        ]
    return out


class FilterOptionsView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="participants_filters", responses={200: dict})
    def get(self, request):
        return Response(configuration.filter_options())


class ParticipantListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(
        operation_id="participants_list",
        parameters=[
            OpenApiParameter(n, str)
            for n in ("q", "status", "programme", "cohort", "county", "offset")
        ],
        responses={200: dict},
    )
    def get(self, request):
        qs, g = _visible(request), request.query_params
        try:
            if g.get("programme"):
                qs = qs.filter(enrollments__programme_id=uuid.UUID(g["programme"]))
            if g.get("cohort"):
                qs = qs.filter(enrollments__cohort_course__cohort_id=uuid.UUID(g["cohort"]))
            if g.get("county"):
                qs = qs.filter(origin_county_id=uuid.UUID(g["county"]))
        except ValueError:
            raise serializers.ValidationError({"filter": ["Invalid filter value."]}) from None
        if g.get("status") in {s for s, _ in Participant.STATUSES}:
            qs = qs.filter(status=g["status"])
        if q := g.get("q", "").strip():
            qs = qs.filter(
                Q(full_name_source__icontains=q) | Q(enrollments__source_enrollment_no__icontains=q)
            )
        qs = qs.distinct().order_by("full_name_source", "pk")
        try:
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            offset = 0
        page = qs.select_related("origin_county").prefetch_related(
            "enrollments__programme", "enrollments__cohort_course__cohort"
        )[offset : offset + PAGE]
        return Response(
            {"total": qs.count(), "page_size": PAGE, "results": [_summary(p) for p in page]}
        )


class ParticipantEditSerializer(serializers.Serializer):
    given_name = serializers.CharField(max_length=100, allow_blank=True, required=False)
    family_name = serializers.CharField(max_length=100, allow_blank=True, required=False)
    other_names = serializers.CharField(max_length=100, allow_blank=True, required=False)
    gender = serializers.ChoiceField(choices=[g for g, _ in Participant.GENDERS], required=False)
    status = serializers.ChoiceField(choices=[s for s, _ in Participant.STATUSES], required=False)


class ParticipantDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "PATCH": EDIT}

    def _get(self, request, pk):
        try:
            return _visible(request).get(pk=pk)
        except Participant.DoesNotExist:
            raise NotFound from None

    @extend_schema(operation_id="participants_detail", responses={200: dict})
    def get(self, request, pk):
        return Response(_detail(self._get(request, pk), request.user))

    @extend_schema(request=ParticipantEditSerializer, responses={200: dict})
    def patch(self, request, pk):
        p = self._get(request, pk)
        s = ParticipantEditSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        before = {k: getattr(p, k) for k in s.validated_data}
        after = {k: v for k, v in s.validated_data.items() if before[k] != v}
        if after:
            for k, v in after.items():
                setattr(p, k, v)
            p.save()
            audit.record(
                actor=request.user,
                action="participant.edited",
                object_type="participant",
                object_id=p.pk,
                before={k: before[k] for k in after},
                after=after,
            )
        return Response(_detail(p, request.user))
