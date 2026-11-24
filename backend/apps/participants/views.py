"""Participant API (T-058, T-043 core): directory, profile, edit. Every query is scoped to the
caller (SEC-06); records outside scope are 404. Contact details need participants.view_contact."""

import datetime
import uuid

from django.db import transaction
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission, has_permission
from apps.api.archive import ARCHIVE, BulkArchiveView
from apps.api.pagination import page_size_of
from apps.audit import services as audit
from apps.configuration import services as configuration

from . import corrections, disability, review_flag, services, similar
from .models import (
    Participant,
    ParticipantContact,
    ParticipantEnrollment,
    ParticipantResidence,
)
from .profile_views import ProfileSerializer

VIEW, EDIT, CONTACT = "participants.view", "participants.edit", "participants.view_contact"


def _visible(request, archived=False):
    return Participant.objects.visible_to(request.user, archived=archived)


current_age = services.current_age


def _summary(p, consent=False):
    enrollments = list(p.enrollments.all())
    out = {
        "id": str(p.pk),
        "name": p.full_name_source,
        "gender": p.gender,
        "age": current_age(p),
        "status": p.status,
        "archived": p.archived_at is not None,
        "review": p.review_state,
        "county": p.origin_county.name if p.origin_county_id else "",
        "projects": sorted({e.project.name for e in enrollments}),
        "cohorts": sorted({e.cohort_course.cohort.name for e in enrollments}),
    }
    if consent:  # only while the consent setting is on
        out["consent"] = p.consent_status
    return out


def _detail(p, user):
    on = services.consent_enabled()
    out = _summary(p, on)
    out.update(
        county_id=str(p.origin_county_id) if p.origin_county_id else "",
        given_name=p.given_name,
        family_name=p.family_name,
        other_names=p.other_names,
        age_basis_date=p.age_basis_date.isoformat() if p.age_basis_date else None,
        date_of_birth=p.date_of_birth.isoformat() if p.date_of_birth else None,
        age_at_source=p.age_at_source,
        review={
            "state": p.review_state,
            "reason": p.review_reason,
            "reason_label": review_flag.REASONS.get(p.review_reason, ""),
            "since": p.review_since.isoformat() if p.review_since else None,
        },
        enrollments=[
            {
                "id": str(e.pk),
                "project": e.project.name,
                "project_id": str(e.project_id),
                "cohort": e.cohort_course.cohort.name,
                "cohort_id": str(e.cohort_course.cohort_id),
                "cohort_course_id": str(e.cohort_course_id),
                "course": e.cohort_course.course.name,
                "institution": e.institution.name,
                "enrollment_no": e.source_enrollment_no,
                "exit_reason": e.exit_reason,
                "extra": e.extra,
                "status": e.status,
                "enrolled_on": e.enrolled_on.isoformat() if e.enrolled_on else None,
                "completed_on": e.completed_on.isoformat() if e.completed_on else None,
            }
            for e in p.enrollments.select_related(
                "project", "institution", "cohort_course__cohort", "cohort_course__course"
            )
        ],
        residences=[
            {
                "county": r.county.name if r.county_id else "",
                "county_id": str(r.county_id) if r.county_id else "",
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
    if on:
        out["consent"] = {
            "status": p.consent_status,
            "label": p.get_consent_status_display(),
            "notice_version": p.consent_notice_version,
            "recorded_on": p.consent_recorded_on.isoformat() if p.consent_recorded_on else None,
        }
    return out


class FilterOptionsView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="participants_filters", responses={200: dict})
    def get(self, request):
        return Response(configuration.filter_options())


class _NewContactSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[ParticipantContact.PHONE, ParticipantContact.EMAIL])
    value = serializers.CharField(max_length=200)
    primary = serializers.BooleanField(default=False)


class _NewResidenceSerializer(serializers.Serializer):
    county_id = serializers.UUIDField(allow_null=True, required=False)
    sub_county = serializers.CharField(max_length=100, allow_blank=True, required=False)
    ward = serializers.CharField(max_length=100, allow_blank=True, required=False)

    def validate_county_id(self, value):
        if value is not None and not configuration.county_exists(value):
            raise serializers.ValidationError("Unknown county.")
        return value


class _NewEnrollmentSerializer(serializers.Serializer):
    cohort_course_id = serializers.UUIDField()
    enrollment_no = serializers.CharField(max_length=60, allow_blank=True, required=False)
    status = serializers.ChoiceField(
        choices=[s for s, _ in ParticipantEnrollment.STATUSES],
        default=ParticipantEnrollment.ENROLLED,
    )
    enrolled_on = serializers.DateField(allow_null=True, required=False)
    completed_on = serializers.DateField(allow_null=True, required=False)
    exit_reason = serializers.CharField(max_length=200, allow_blank=True, required=False)
    qualification_code = serializers.CharField(max_length=60, allow_blank=True, required=False)
    referral_source_code = serializers.CharField(max_length=60, allow_blank=True, required=False)
    extra = serializers.DictField(
        child=serializers.CharField(max_length=services.MAX_EXTRA_VALUE, allow_blank=True),
        required=False,
    )

    def validate_extra(self, value):
        for k in value:
            if not 0 < len(k.strip()) <= services.MAX_EXTRA_LABEL:
                raise serializers.ValidationError("Each extra detail needs a short label.")
        return {k.strip(): v for k, v in value.items() if v.strip()}


class ParticipantCreateSerializer(serializers.Serializer):
    full_name_source = serializers.CharField(max_length=200)
    given_name = serializers.CharField(max_length=100, allow_blank=True, required=False)
    family_name = serializers.CharField(max_length=100, allow_blank=True, required=False)
    other_names = serializers.CharField(max_length=100, allow_blank=True, required=False)
    gender = serializers.ChoiceField(
        choices=[g for g, _ in Participant.GENDERS], default=Participant.GENDER_UNKNOWN
    )
    status = serializers.ChoiceField(
        choices=[s for s, _ in Participant.STATUSES], default=Participant.UNKNOWN
    )
    date_of_birth = serializers.DateField(allow_null=True, required=False)
    age_at_source = serializers.IntegerField(
        min_value=0, max_value=120, allow_null=True, required=False
    )
    age_basis_date = serializers.DateField(allow_null=True, required=False)
    origin_county_id = serializers.UUIDField(allow_null=True, required=False)
    residence = _NewResidenceSerializer(required=False)
    contacts = _NewContactSerializer(many=True, max_length=20, required=False)
    source_id = serializers.CharField(max_length=100, allow_blank=True, required=False)
    source_name = serializers.CharField(max_length=60, allow_blank=True, required=False)
    enrollment = _NewEnrollmentSerializer(required=False)
    capability = ProfileSerializer(required=False)

    def validate_origin_county_id(self, value):
        if value is not None and not configuration.county_exists(value):
            raise serializers.ValidationError("Unknown county.")
        return value

    def validate_contacts(self, rows):
        if rows and not has_permission(self.context["request"].user, CONTACT):
            raise serializers.ValidationError("You may not add contact details.")
        for kind in (ParticipantContact.PHONE, ParticipantContact.EMAIL):
            if sum(1 for r in rows if r["kind"] == kind and r["primary"]) > 1:
                raise serializers.ValidationError(f"Only one primary {kind} is allowed.")
        return rows

    def validate(self, attrs):
        if attrs.get("source_id") and not attrs.get("source_name", "").strip():
            raise serializers.ValidationError({"source_name": "Say which system the ID is from."})
        return attrs


class NameCheckView(APIView):
    """Who already looks like this youth, so a duplicate is noticed before saving (T-055).
    Names are compared loosely; a phone number or date of birth sharpens the match. It only
    warns: the caller decides whether to go ahead."""

    permission_classes = [HasPermission]
    required_permission = {"GET": EDIT}

    @extend_schema(
        operation_id="participants_check_name",
        parameters=[
            OpenApiParameter("name", str),
            OpenApiParameter("phone", str),
            OpenApiParameter("dob", str),
        ],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        phone = g.get("phone", "") if has_permission(request.user, CONTACT) else ""
        try:
            dob = datetime.date.fromisoformat(g["dob"]) if g.get("dob") else None
        except ValueError:
            dob = None
        matches = similar.similar_to(
            name=g.get("name", ""), scope=_visible(request), phone=phone, birth_date=dob
        )
        return Response({"matches": matches})


class ParticipantListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "POST": EDIT}

    @extend_schema(
        operation_id="participants_create",
        request=ParticipantCreateSerializer,
        responses={201: dict},
    )
    def post(self, request):
        s = ParticipantCreateSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        try:
            p = services.create_participant(actor=request.user, data=s.validated_data)
        except services.CreateError as exc:
            raise serializers.ValidationError({exc.field: [exc.message]}) from exc
        p = _visible(request, archived=None).filter(pk=p.pk).first() or p
        return Response(_detail(p, request.user), status=201)

    @extend_schema(
        operation_id="participants_list",
        parameters=[
            OpenApiParameter(n, str)
            for n in (
                "q",
                "status",
                "project",
                "cohort",
                "county",
                "review",
                "archived",
                "offset",
                "page_size",
            )
        ],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        try:
            qs, fuzzy = services.filtered(request.user, g)
        except services.FilterError as exc:
            raise serializers.ValidationError({"filter": [str(exc)]}) from None
        size = page_size_of(g)
        try:
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            offset = 0
        page = qs.select_related("origin_county").prefetch_related(
            "enrollments__project", "enrollments__cohort_course__cohort"
        )[offset : offset + size]
        consent = services.consent_enabled()
        return Response(
            {
                "total": qs.count(),
                "page_size": size,
                "similar_names": fuzzy,
                "results": [_summary(p, consent) for p in page],
            }
        )


class ParticipantEditSerializer(serializers.Serializer):
    full_name_source = serializers.CharField(max_length=200, required=False)
    date_of_birth = serializers.DateField(allow_null=True, required=False)
    age_at_source = serializers.IntegerField(
        min_value=0, max_value=120, allow_null=True, required=False
    )
    origin_county_id = serializers.UUIDField(allow_null=True, required=False)

    def validate_origin_county_id(self, value):
        if value is not None and not configuration.county_exists(value):
            raise serializers.ValidationError("Unknown county.")
        return value

    given_name = serializers.CharField(max_length=100, allow_blank=True, required=False)
    family_name = serializers.CharField(max_length=100, allow_blank=True, required=False)
    other_names = serializers.CharField(max_length=100, allow_blank=True, required=False)
    gender = serializers.ChoiceField(choices=[g for g, _ in Participant.GENDERS], required=False)
    status = serializers.ChoiceField(choices=[s for s, _ in Participant.STATUSES], required=False)


class ParticipantDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "PATCH": EDIT, "DELETE": ARCHIVE}

    def _get(self, request, pk):
        try:
            return _visible(request, archived=None).get(pk=pk)
        except Participant.DoesNotExist:
            raise NotFound from None

    @extend_schema(operation_id="participants_detail", responses={200: dict})
    def get(self, request, pk):
        return Response(_detail(self._get(request, pk), request.user))

    @extend_schema(operation_id="participants_archive", responses={200: dict})
    def delete(self, request, pk):
        """Archive (soft delete). Restore with POST /participants/restore."""
        self._get(request, pk)  # 404 outside the caller's scope
        return Response(
            audit.set_archived(
                actor=request.user,
                queryset=_visible(request, archived=None),
                ids=[pk],
                archive=True,
                object_type="participant",
            )
        )

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
            corrections.record(
                actor=request.user,
                participant=p,
                changes={
                    corrections.PARTICIPANT_FIELDS[k]: (before[k], v)
                    for k, v in after.items()
                    if k in corrections.PARTICIPANT_FIELDS
                },
            )

            def plain(x):  # audit payloads are JSON: dates and ids become text
                if hasattr(x, "isoformat"):
                    return x.isoformat()
                return str(x) if isinstance(x, uuid.UUID) else x

            audit.record(
                actor=request.user,
                action="participant.edited",
                object_type="participant",
                object_id=p.pk,
                before={k: plain(before[k]) for k in after},
                after={k: plain(v) for k, v in after.items()},
            )
        return Response(_detail(p, request.user))


class EnrollmentEditSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[s for s, _ in ParticipantEnrollment.STATUSES], required=False
    )
    source_enrollment_no = serializers.CharField(max_length=60, allow_blank=True, required=False)
    enrolled_on = serializers.DateField(allow_null=True, required=False)
    completed_on = serializers.DateField(allow_null=True, required=False)
    exit_reason = serializers.CharField(max_length=200, allow_blank=True, required=False)
    # Moving to another cohort/course; project and institution follow the cohort.
    cohort_course_id = serializers.UUIDField(required=False)


class EnrollmentCreateView(APIView):
    """Add a further enrollment (e.g. another course completed) to an existing youth."""

    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT}

    @extend_schema(
        operation_id="participants_enrollment_add",
        request=_NewEnrollmentSerializer,
        responses={201: dict},
    )
    def post(self, request, pk):
        try:
            p = _visible(request, archived=None).get(pk=pk)
        except Participant.DoesNotExist:
            raise NotFound from None
        s = _NewEnrollmentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        ids = configuration.offering_ids(d["cohort_course_id"])
        if ids is None:
            raise serializers.ValidationError({"cohort_course_id": "Unknown course offering."})
        if p.enrollments.filter(cohort_course_id=d["cohort_course_id"]).exists():
            raise serializers.ValidationError(
                {"cohort_course_id": "This youth is already enrolled in that course."}
            )
        no = d.get("enrollment_no", "").strip()
        if (
            no
            and ParticipantEnrollment.objects.filter(
                project_id=ids[0], source_enrollment_no=no
            ).exists()
        ):
            raise serializers.ValidationError(
                {"enrollment_no": "Another enrollment in this project has that number."}
            )
        e = ParticipantEnrollment.objects.create(
            participant=p,
            cohort_course_id=d["cohort_course_id"],
            project_id=ids[0],
            institution_id=ids[1],
            source_enrollment_no=no,
            status=d["status"],
            enrolled_on=d.get("enrolled_on"),
            completed_on=d.get("completed_on"),
            exit_reason=d.get("exit_reason", ""),
            source_qualification_code=d.get("qualification_code", ""),
            referral_source_code=d.get("referral_source_code", ""),
            extra=d.get("extra") or {},
        )
        audit.record(
            actor=request.user,
            action="participant.enrollment_added",
            object_type="participant",
            object_id=p.pk,
            after={
                "cohort_course_id": str(e.cohort_course_id),
                "status": e.status,
                "enrollment_no": e.source_enrollment_no,
            },
        )
        return Response(_detail(p, request.user), status=201)


class EnrollmentDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"PATCH": EDIT}

    @extend_schema(
        operation_id="participants_enrollment_edit",
        request=EnrollmentEditSerializer,
        responses={200: dict},
    )
    def patch(self, request, pk, enrollment_id):
        try:
            p = _visible(request, archived=None).get(pk=pk)
            e = p.enrollments.get(pk=enrollment_id)
        except (Participant.DoesNotExist, ParticipantEnrollment.DoesNotExist):
            raise NotFound from None
        s = EnrollmentEditSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        offering = data.pop("cohort_course_id", None)
        before = {k: getattr(e, k) for k in data}
        after = {k: v for k, v in data.items() if before[k] != v}
        project_id = e.project_id
        if offering is not None and offering != e.cohort_course_id:
            ids = configuration.offering_ids(offering)
            if ids is None:
                raise serializers.ValidationError({"cohort_course_id": "Unknown course offering."})
            if p.enrollments.filter(cohort_course_id=offering).exclude(pk=e.pk).exists():
                raise serializers.ValidationError(
                    {"cohort_course_id": "This youth is already enrolled in that course."}
                )
            before["cohort_course_id"] = str(e.cohort_course_id)
            before["project_id"] = str(e.project_id)
            before["institution_id"] = str(e.institution_id)
            after["cohort_course_id"] = offering
            after["project_id"], after["institution_id"] = ids
            project_id = ids[0]
        # A number is checked against the project it will belong to after the change.
        no = after.get("source_enrollment_no")
        if no is None and project_id != e.project_id:
            no = e.source_enrollment_no
        if (
            no
            and ParticipantEnrollment.objects.filter(project=project_id, source_enrollment_no=no)
            .exclude(pk=e.pk)
            .exists()
        ):
            raise serializers.ValidationError(
                {"source_enrollment_no": "Another enrollment in this project has that number."}
            )
        if after:
            for k, v in after.items():
                setattr(e, k, v)
            e.save()
            if "status" in after:
                corrections.record(
                    actor=request.user,
                    participant=p,
                    changes={"status": (before["status"], after["status"])},
                    enrollment=e,
                )

            def plain(x):
                if hasattr(x, "isoformat"):
                    return x.isoformat()
                return str(x) if isinstance(x, uuid.UUID) else x

            audit.record(
                actor=request.user,
                action="participant.enrollment_edited",
                object_type="participant",
                object_id=p.pk,
                before={k: plain(before[k]) for k in after},
                after={k: plain(v) for k, v in after.items()},
            )
        return Response(_detail(p, request.user))


class ParticipantContactSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[ParticipantContact.PHONE, ParticipantContact.EMAIL])
    value = serializers.CharField(max_length=200)
    primary = serializers.BooleanField(default=False)


class ParticipantContactsSerializer(serializers.Serializer):
    contacts = ParticipantContactSerializer(many=True, max_length=20)

    def validate_contacts(self, rows):
        for kind in (ParticipantContact.PHONE, ParticipantContact.EMAIL):
            if sum(1 for r in rows if r["kind"] == kind and r["primary"]) > 1:
                raise serializers.ValidationError(f"Only one primary {kind} is allowed.")
        return rows


class ConsentSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Participant.CONSENTS)
    notice_version = serializers.CharField(max_length=40, allow_blank=True, default="")
    recorded_on = serializers.DateField(required=False)

    def validate(self, attrs):
        if attrs["status"] == Participant.CONSENT_NOT_RECORDED:
            return {"status": attrs["status"], "notice_version": "", "recorded_on": None}
        version = attrs["notice_version"].strip()
        if not version:
            raise serializers.ValidationError({"notice_version": ["Say which notice version."]})
        on = attrs.get("recorded_on") or timezone.localdate()
        if on > timezone.localdate():
            raise serializers.ValidationError(
                {"recorded_on": ["The date cannot be in the future."]}
            )
        return {"status": attrs["status"], "notice_version": version, "recorded_on": on}


class ConsentView(APIView):
    """Record a youth's privacy-notice consent status (T-054). Needs participants.edit, and the
    ``consent_tracking`` setting must be on: with it off the route does not exist (404)."""

    permission_classes = [HasPermission]
    required_permission = {"PUT": EDIT}

    @extend_schema(
        operation_id="participants_consent_record", request=ConsentSerializer, responses={200: dict}
    )
    def put(self, request, pk):
        if not services.consent_enabled():
            raise NotFound
        try:
            p = _visible(request, archived=None).get(pk=pk)
        except Participant.DoesNotExist:
            raise NotFound from None
        s = ConsentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        def snap():
            return {
                "status": p.consent_status,
                "notice_version": p.consent_notice_version,
                "recorded_on": p.consent_recorded_on.isoformat() if p.consent_recorded_on else None,
            }

        before = snap()
        p.consent_status = d["status"]
        p.consent_notice_version = d["notice_version"]
        p.consent_recorded_on = d["recorded_on"]
        p.save()
        audit.record(
            actor=request.user,
            action="participant.consent_recorded",
            object_type="participant",
            object_id=p.pk,
            before=before,
            after=snap(),
        )
        return Response(_detail(p, request.user))


class ContactsView(APIView):
    """Replace a participant's contact list. Needs participants.edit and view_contact."""

    permission_classes = [HasPermission]
    required_permission = {"PUT": EDIT}

    @extend_schema(
        operation_id="participants_contacts_replace",
        request=ParticipantContactsSerializer,
        responses={200: dict},
    )
    def put(self, request, pk):
        if not has_permission(request.user, CONTACT):
            raise PermissionDenied
        try:
            p = _visible(request, archived=None).get(pk=pk)
        except Participant.DoesNotExist:
            raise NotFound from None
        s = ParticipantContactsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        rows = s.validated_data["contacts"]
        old = [{"kind": c.kind, "primary": c.is_primary} for c in p.contacts.all()]
        new = [{"kind": r["kind"], "primary": r["primary"]} for r in rows]
        with transaction.atomic():
            p.contacts.all().delete()
            ParticipantContact.objects.bulk_create(
                ParticipantContact(
                    participant=p, kind=r["kind"], value=r["value"].strip(), is_primary=r["primary"]
                )
                for r in rows
            )
            # Values are personal data, so the audit trail records counts and kinds, not numbers.
            audit.record(
                actor=request.user,
                action="participant.contacts_edited",
                object_type="participant",
                object_id=p.pk,
                before={"contacts": old},
                after={"contacts": new},
            )
        return Response(_detail(p, request.user))


class ResidenceSerializer(serializers.Serializer):
    county_id = serializers.UUIDField(allow_null=True, required=False)
    sub_county = serializers.CharField(max_length=100, allow_blank=True, required=False)
    ward = serializers.CharField(max_length=100, allow_blank=True, required=False)

    def validate_county_id(self, value):
        if value is not None and not configuration.county_exists(value):
            raise serializers.ValidationError("Unknown county.")
        return value


class ResidenceView(APIView):
    """Set the current residence. The previous one is closed, so the history is kept."""

    permission_classes = [HasPermission]
    required_permission = {"PUT": EDIT}

    @extend_schema(
        operation_id="participants_residence_set",
        request=ResidenceSerializer,
        responses={200: dict},
    )
    def put(self, request, pk):
        try:
            p = _visible(request, archived=None).get(pk=pk)
        except Participant.DoesNotExist:
            raise NotFound from None
        s = ResidenceSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        current = p.residences.filter(valid_to__isnull=True).first()
        county_id = d.get("county_id", current.county_id if current else None)
        sub = d.get("sub_county", current.sub_county_source if current else "")
        ward = d.get("ward", current.ward_source if current else "")
        same = current and (current.county_id, current.sub_county_source, current.ward_source) == (
            county_id,
            sub,
            ward,
        )
        if not same:
            with transaction.atomic():
                if current:
                    current.valid_to = timezone.localdate()
                    current.save(update_fields=["valid_to"])
                ParticipantResidence.objects.create(
                    participant=p,
                    county_id=county_id,
                    sub_county_source=sub,
                    ward_source=ward,
                    valid_from=timezone.localdate(),
                )
                audit.record(
                    actor=request.user,
                    action="participant.residence_edited",
                    object_type="participant",
                    object_id=p.pk,
                    before={"county_id": str(current.county_id or "") if current else ""},
                    after={"county_id": str(county_id or "")},
                )
        return Response(_detail(p, request.user))


class DisabilitySerializer(serializers.Serializer):
    disability = serializers.ChoiceField(choices=Participant.DISABILITY_VALUES)
    description = serializers.CharField(max_length=300, allow_blank=True, required=False)


class FlagGate(BasePermission):
    """With the flag off the route does not exist (404). Put after HasPermission."""

    def has_permission(self, request, view):
        if not services.flag_enabled(view.required_flag, request.user):
            raise Http404
        return True


class DisabilityView(APIView):
    """Read or record whether a youth has a disability (NEW-040, NEW-073). Behind the flag
    ``participants.disability`` (off: 404) and the permission ``participants.view_disability``;
    reading also needs ``participants.view`` and writing ``participants.edit``. Every call is
    written to the audit log without the answer."""

    permission_classes = [HasPermission, FlagGate]
    required_permission = {"GET": VIEW, "PUT": EDIT}
    required_flag = disability.FLAG

    def _youth(self, request, pk):
        if not has_permission(request.user, disability.PERMISSION):
            raise PermissionDenied
        try:
            return _visible(request, archived=None).get(pk=pk)
        except Participant.DoesNotExist:
            raise NotFound from None

    @extend_schema(operation_id="participants_disability_get", responses={200: dict})
    def get(self, request, pk):
        return Response(disability.read(actor=request.user, p=self._youth(request, pk)))

    @extend_schema(
        operation_id="participants_disability_set",
        request=DisabilitySerializer,
        responses={200: dict},
    )
    def put(self, request, pk):
        p = self._youth(request, pk)
        s = DisabilitySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            doc = disability.write(
                actor=request.user,
                p=p,
                answer=d["disability"],
                description=d.get("description", ""),
            )
        except disability.DisabilityError as e:
            raise serializers.ValidationError({e.field: str(e)}) from None
        return Response(doc)


class ParticipantArchiveView(BulkArchiveView):
    def run(self, request, ids, reason):
        return audit.set_archived(
            actor=request.user,
            queryset=_visible(request, archived=None),
            ids=ids,
            archive=self.archive,
            object_type="participant",
            reason=reason,
        )


class ParticipantRestoreView(ParticipantArchiveView):
    archive = False


class ReviewNoteSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")


class ReviewBulkSerializer(ReviewNoteSerializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=500)


class ParticipantReviewView(APIView):
    """The review flag on one youth (D-084). GET the history; POST an officer flag (reason
    required); DELETE marks it reviewed. Blocks nothing."""

    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "POST": EDIT, "DELETE": EDIT}

    def _get(self, request, pk):
        try:
            return _visible(request, archived=None).get(pk=pk)
        except Participant.DoesNotExist:
            raise NotFound from None

    @extend_schema(operation_id="participants_review_history", responses={200: dict})
    def get(self, request, pk):
        return Response({"results": review_flag.history(self._get(request, pk))})

    @extend_schema(request=ReviewNoteSerializer, responses={200: dict})
    def post(self, request, pk):
        p = self._get(request, pk)
        s = ReviewNoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            review_flag.officer_flag(actor=request.user, p=p, note=s.validated_data["note"])
        except review_flag.ReviewError as exc:
            raise serializers.ValidationError({exc.field: [str(exc)]}) from None
        return Response({"state": Participant.REVIEW_NEEDED})

    @extend_schema(request=ReviewNoteSerializer, responses={200: dict})
    def delete(self, request, pk):
        p = self._get(request, pk)
        s = ReviewNoteSerializer(data=request.data or {})
        s.is_valid(raise_exception=True)
        n = review_flag.mark_reviewed(
            actor=request.user, participants=[p], note=s.validated_data["note"]
        )
        return Response({"marked": n})


class ParticipantReviewBulkView(APIView):
    """Mark many youth reviewed at once. Ids outside the caller's scope are ignored."""

    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT}

    @extend_schema(request=ReviewBulkSerializer, responses={200: dict})
    def post(self, request):
        s = ReviewBulkSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        rows = list(_visible(request, archived=None).filter(pk__in=s.validated_data["ids"]))
        n = review_flag.mark_reviewed(
            actor=request.user, participants=rows, note=s.validated_data["note"]
        )
        return Response({"marked": n})
