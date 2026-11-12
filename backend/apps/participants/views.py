"""Participant API (T-058, T-043 core): directory, profile, edit. Every query is scoped to the
caller (SEC-06); records outside scope are 404. Contact details need participants.view_contact."""

import uuid

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission, has_permission
from apps.api.archive import ARCHIVE, BulkArchiveView
from apps.api.pagination import page_size_of
from apps.audit import services as audit
from apps.configuration import services as configuration

from . import services
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


def current_age(p):
    """Age today from the date of birth; the source file's age only when there is none."""
    dob = p.date_of_birth
    if not dob:
        return p.age_at_source
    today = timezone.localdate()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _summary(p):
    enrollments = list(p.enrollments.all())
    return {
        "id": str(p.pk),
        "name": p.full_name_source,
        "gender": p.gender,
        "age": current_age(p),
        "status": p.status,
        "archived": p.archived_at is not None,
        "county": p.origin_county.name if p.origin_county_id else "",
        "programmes": sorted({e.programme.name for e in enrollments}),
        "cohorts": sorted({e.cohort_course.cohort.name for e in enrollments}),
    }


def _detail(p, user):
    out = _summary(p)
    out.update(
        county_id=str(p.origin_county_id) if p.origin_county_id else "",
        given_name=p.given_name,
        family_name=p.family_name,
        other_names=p.other_names,
        age_basis_date=p.age_basis_date.isoformat() if p.age_basis_date else None,
        date_of_birth=p.date_of_birth.isoformat() if p.date_of_birth else None,
        age_at_source=p.age_at_source,
        enrollments=[
            {
                "id": str(e.pk),
                "programme": e.programme.name,
                "programme_id": str(e.programme_id),
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
                "programme", "institution", "cohort_course__cohort", "cohort_course__course"
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
    """Similar names already in the caller's scope, so a duplicate is noticed before saving."""

    permission_classes = [HasPermission]
    required_permission = {"GET": EDIT}

    @extend_schema(
        operation_id="participants_check_name",
        parameters=[OpenApiParameter("name", str)],
        responses={200: dict},
    )
    def get(self, request):
        name = request.query_params.get("name", "").strip()
        if len(name) < 3:
            return Response({"matches": []})
        qs = _visible(request).filter(full_name_source__iexact=name)[:5]
        return Response(
            {
                "matches": [
                    {"id": str(p.pk), "name": p.full_name_source, "status": p.status} for p in qs
                ]
            }
        )


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
                "programme",
                "cohort",
                "county",
                "archived",
                "offset",
                "page_size",
            )
        ],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        qs = _visible(request, archived=g.get("archived") == "1")
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
        size = page_size_of(g)
        try:
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            offset = 0
        page = qs.select_related("origin_county").prefetch_related(
            "enrollments__programme", "enrollments__cohort_course__cohort"
        )[offset : offset + size]
        return Response(
            {"total": qs.count(), "page_size": size, "results": [_summary(p) for p in page]}
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
    # Moving to another cohort/course; programme and institution follow the cohort.
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
                programme_id=ids[0], source_enrollment_no=no
            ).exists()
        ):
            raise serializers.ValidationError(
                {"enrollment_no": "Another enrollment in this programme has that number."}
            )
        e = ParticipantEnrollment.objects.create(
            participant=p,
            cohort_course_id=d["cohort_course_id"],
            programme_id=ids[0],
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
        programme_id = e.programme_id
        if offering is not None and offering != e.cohort_course_id:
            ids = configuration.offering_ids(offering)
            if ids is None:
                raise serializers.ValidationError({"cohort_course_id": "Unknown course offering."})
            if p.enrollments.filter(cohort_course_id=offering).exclude(pk=e.pk).exists():
                raise serializers.ValidationError(
                    {"cohort_course_id": "This youth is already enrolled in that course."}
                )
            before["cohort_course_id"] = str(e.cohort_course_id)
            before["programme_id"] = str(e.programme_id)
            before["institution_id"] = str(e.institution_id)
            after["cohort_course_id"] = offering
            after["programme_id"], after["institution_id"] = ids
            programme_id = ids[0]
        # A number is checked against the programme it will belong to after the change.
        no = after.get("source_enrollment_no")
        if no is None and programme_id != e.programme_id:
            no = e.source_enrollment_no
        if (
            no
            and ParticipantEnrollment.objects.filter(
                programme=programme_id, source_enrollment_no=no
            )
            .exclude(pk=e.pk)
            .exists()
        ):
            raise serializers.ValidationError(
                {"source_enrollment_no": "Another enrollment in this programme has that number."}
            )
        if after:
            for k, v in after.items():
                setattr(e, k, v)
            e.save()

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
