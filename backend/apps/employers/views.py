"""Employer API (T-044, FR-11). employers.view reads, employers.edit changes."""

import uuid

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission
from apps.api.archive import ARCHIVE, BulkArchiveView, archived_filter
from apps.api.pagination import page_size_of
from apps.audit import services as audit
from apps.configuration import services as configuration

from . import services
from .models import Employer, EmployerContact, Opportunity, OpportunityRequirement

VIEW, EDIT = "employers.view", "employers.edit"


def _archive_one(request, queryset, pk, object_type):
    result = audit.set_archived(
        actor=request.user, queryset=queryset, ids=[pk], archive=True, object_type=object_type
    )
    if not result["changed"] and result["skipped"][0]["reason"] == "Not found.":
        raise NotFound
    return result


class EmployerArchiveView(BulkArchiveView):
    def run(self, request, ids, reason):
        return audit.set_archived(
            actor=request.user,
            queryset=Employer.objects.all(),
            ids=ids,
            archive=self.archive,
            object_type="employer",
            reason=reason,
        )


class EmployerRestoreView(EmployerArchiveView):
    archive = False


class OpportunityArchiveView(BulkArchiveView):
    def run(self, request, ids, reason):
        return audit.set_archived(
            actor=request.user,
            queryset=Opportunity.objects.all(),
            ids=ids,
            archive=self.archive,
            object_type="opportunity",
            reason=reason,
        )


class OpportunityRestoreView(OpportunityArchiveView):
    archive = False


def _summary(e):
    return {
        "id": str(e.pk),
        "name": e.name,
        "status": e.status,
        "sector": e.sector.name if e.sector_id else "",
        "county": e.county.name if e.county_id else "",
        "archived": e.archived_at is not None,
    }


def _contact(c):
    return {
        "id": str(c.pk), "name": c.name, "role": c.role, "email": c.email,
        "phone": c.phone, "is_primary": c.is_primary,
    }  # fmt: skip


def _detail(e):
    return {
        **_summary(e),
        "sector_id": str(e.sector_id) if e.sector_id else None,
        "county_id": str(e.county_id) if e.county_id else None,
        "sub_county": e.sub_county,
        "address": e.address,
        "website": e.website,
        "notes": e.notes,
        "contacts": [_contact(c) for c in e.contacts.all()],
    }


class EmployerSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    sector_id = serializers.UUIDField(required=False, allow_null=True)
    county_id = serializers.UUIDField(required=False, allow_null=True)
    sub_county = serializers.CharField(max_length=100, required=False, allow_blank=True)
    address = serializers.CharField(max_length=200, required=False, allow_blank=True)
    website = serializers.CharField(max_length=200, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=Employer.STATUSES, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    confirm_duplicate = serializers.BooleanField(required=False, default=False)

    def validate_name(self, value):
        value = value.strip()
        if not services.norm(value):
            raise serializers.ValidationError("Name is required.")
        return value


class ContactSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    role = serializers.CharField(max_length=100, required=False, allow_blank=True)
    email = serializers.EmailField(max_length=200, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    is_primary = serializers.BooleanField(required=False, default=False)


def _duplicate_response(exc):
    return Response(
        {
            "errors": [
                {
                    "field": "name",
                    "message": "A similar employer already exists.",
                    "code": "duplicate_name",
                }
            ],
            "matches": exc.matches,
        },
        status=status.HTTP_409_CONFLICT,
    )


def _get(pk):
    try:
        return Employer.objects.select_related("sector", "county").get(pk=pk)
    except Employer.DoesNotExist:
        raise NotFound from None


def _save(request, employer=None):
    s = EmployerSerializer(data=request.data, partial=employer is not None)
    s.is_valid(raise_exception=True)
    data = dict(s.validated_data)
    confirm = data.pop("confirm_duplicate", False)
    try:
        if employer is None:
            return services.create_employer(
                actor=request.user, data=data, confirm_duplicate=confirm
            )
        return services.update_employer(
            actor=request.user, employer=employer, data=data, confirm_duplicate=confirm
        )
    except services.DuplicateWarning as exc:
        return exc


class EmployerListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "POST": EDIT}

    @extend_schema(
        operation_id="employers_list",
        parameters=[
            OpenApiParameter(n, str)
            for n in ("q", "status", "sector", "county", "archived", "offset", "page_size")
        ],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        qs = archived_filter(Employer.objects.select_related("sector", "county"), g)
        if q := g.get("q", "").strip():
            qs = qs.filter(name_normalised__contains=services.norm(q))
        if g.get("status") in {s for s, _ in Employer.STATUSES}:
            qs = qs.filter(status=g["status"])
        try:
            if g.get("sector"):
                qs = qs.filter(sector_id=uuid.UUID(g["sector"]))
            if g.get("county"):
                qs = qs.filter(county_id=uuid.UUID(g["county"]))
        except ValueError:
            raise serializers.ValidationError({"filter": ["Invalid filter value."]}) from None
        size = page_size_of(g)
        try:
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            offset = 0
        size = page_size_of(g)
        return Response(
            {
                "total": qs.count(),
                "page_size": size,
                "results": [_summary(e) for e in qs[offset : offset + size]],
            }
        )

    @extend_schema(request=EmployerSerializer, responses={201: dict, 409: dict})
    def post(self, request):
        result = _save(request)
        if isinstance(result, services.DuplicateWarning):
            return _duplicate_response(result)
        return Response(_detail(_get(result.pk)), status=status.HTTP_201_CREATED)


class EmployerDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "PATCH": EDIT, "DELETE": ARCHIVE}

    @extend_schema(operation_id="employers_detail", responses={200: dict})
    def get(self, request, pk):
        return Response(_detail(_get(pk)))

    @extend_schema(operation_id="employers_archive", responses={200: dict})
    def delete(self, request, pk):
        """Archive (soft delete). Restore with POST /employers/restore."""
        return Response(_archive_one(request, Employer.objects.all(), pk, "employer"))

    @extend_schema(request=EmployerSerializer, responses={200: dict, 409: dict})
    def patch(self, request, pk):
        result = _save(request, _get(pk))
        if isinstance(result, services.DuplicateWarning):
            return _duplicate_response(result)
        return Response(_detail(_get(pk)))


class EmployerCheckView(APIView):
    """Duplicate-name check the form calls while typing."""

    permission_classes = [HasPermission]
    required_permission = {"GET": EDIT}

    @extend_schema(
        operation_id="employers_check_name",
        parameters=[OpenApiParameter("name", str), OpenApiParameter("exclude", str)],
        responses={200: dict},
    )
    def get(self, request):
        try:
            exclude = (
                uuid.UUID(request.query_params["exclude"])
                if request.query_params.get("exclude")
                else None
            )
        except ValueError:
            raise serializers.ValidationError({"exclude": ["Invalid id."]}) from None
        matches = services.find_similar(request.query_params.get("name", ""), exclude=exclude)
        return Response({"matches": matches})


class EmployerHistoryView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="employers_history", responses={200: dict(type="array", items={})})
    def get(self, request, pk):
        return Response(services.history(_get(pk)))


class ContactListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT}

    @extend_schema(request=ContactSerializer, responses={201: dict})
    def post(self, request, pk):
        e = _get(pk)
        s = ContactSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        c = services.save_contact(actor=request.user, employer=e, data=s.validated_data)
        return Response(_contact(c), status=status.HTTP_201_CREATED)


class ContactDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"PATCH": EDIT, "DELETE": EDIT}

    def _contact(self, pk, cpk):
        e = _get(pk)
        try:
            return e, e.contacts.get(pk=cpk)
        except EmployerContact.DoesNotExist:
            raise NotFound from None

    @extend_schema(request=ContactSerializer, responses={200: dict})
    def patch(self, request, pk, cpk):
        e, c = self._contact(pk, cpk)
        s = ContactSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        c = services.save_contact(actor=request.user, employer=e, data=s.validated_data, contact=c)
        return Response(_contact(c))

    @extend_schema(responses={204: None})
    def delete(self, request, pk, cpk):
        e, c = self._contact(pk, cpk)
        services.remove_contact(actor=request.user, employer=e, contact=c)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FilterOptionsView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="employers_filters", responses={200: dict})
    def get(self, request):
        o = configuration.filter_options()
        return Response({"sectors": o["sectors"], "counties": o["counties"]})


# --- opportunities (T-045) -------------------------------------------------------------------


def _violation(exc):
    return Response(
        {"errors": [{"field": exc.field, "message": exc.message, "code": exc.code}]},
        status=status.HTTP_409_CONFLICT,
    )


def _req(r):
    return {
        "id": str(r.pk), "factor": r.factor, "description": r.description,
        "is_mandatory": r.is_mandatory,
        "qualification_level_id": (
            str(r.qualification_level_id) if r.qualification_level_id else None
        ),
        "min_grade_id": str(r.min_grade_id) if r.min_grade_id else None,
        "skill_id": str(r.skill_id) if r.skill_id else None,
        "min_months": r.min_months,
        "needed_by": r.needed_by.isoformat() if r.needed_by else None,
        "work_pattern": r.work_pattern,
        "needs_structuring": r.needs_structuring,
    }  # fmt: skip


def _opp_summary(o):
    return {
        "id": str(o.pk),
        "title": o.title,
        "employer_id": str(o.employer_id),
        "employer": o.employer.name,
        "kind": o.kind,
        "status": o.status,
        "county": o.county.name if o.county_id else "",
        "positions": o.positions,
        "closing_date": o.closing_date.isoformat() if o.closing_date else None,
        "archived": o.archived_at is not None,
    }


def _opp_detail(o):
    return {
        **_opp_summary(o),
        "sector": o.sector.name if o.sector_id else "",
        "sector_id": str(o.sector_id) if o.sector_id else None,
        "county_id": str(o.county_id) if o.county_id else None,
        "location": o.location,
        "description": o.description,
        "start_date": o.start_date.isoformat() if o.start_date else None,
        "requirements": [_req(r) for r in o.requirements.all()],
        "requirement_options": {
            **{k: v for k, v in configuration.profile_options().items() if k != "sectors"},
            "work_patterns": [
                {"id": k, "name": n.capitalize()} for k, n in services.PATTERN_NAMES.items()
            ],
        },
    }


def _opp(pk):
    try:
        return Opportunity.objects.select_related("employer", "sector", "county").get(pk=pk)
    except Opportunity.DoesNotExist:
        raise NotFound from None


class OpportunitySerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    kind = serializers.ChoiceField(choices=Opportunity.TYPES, required=False)
    sector_id = serializers.UUIDField(required=False, allow_null=True)
    county_id = serializers.UUIDField(required=False, allow_null=True)
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)
    positions = serializers.IntegerField(min_value=1, max_value=10000, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    start_date = serializers.DateField(required=False, allow_null=True)
    closing_date = serializers.DateField(required=False, allow_null=True)


class OpportunityCreateSerializer(OpportunitySerializer):
    employer_id = serializers.UUIDField()


class TransitionSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=[Opportunity.OPEN, Opportunity.CLOSED])
    reason = serializers.CharField(required=False, allow_blank=True)


class RequirementSerializer(serializers.Serializer):
    factor = serializers.ChoiceField(choices=OpportunityRequirement.FACTORS)
    description = serializers.CharField(max_length=300, required=False, allow_blank=True)
    is_mandatory = serializers.BooleanField(required=False, default=False)
    qualification_level_id = serializers.UUIDField(required=False, allow_null=True)
    min_grade_id = serializers.UUIDField(required=False, allow_null=True)
    skill_id = serializers.UUIDField(required=False, allow_null=True)
    min_months = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=600
    )
    needed_by = serializers.DateField(required=False, allow_null=True)
    work_pattern = serializers.CharField(required=False, allow_blank=True, max_length=20)


class OpportunityListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "POST": EDIT}

    @extend_schema(
        operation_id="opportunities_list",
        parameters=[
            OpenApiParameter(n, str)
            for n in ("q", "status", "employer", "kind", "archived", "offset", "page_size")
        ],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        qs = archived_filter(Opportunity.objects.select_related("employer", "county"), g)
        if g.get("archived") != "1":  # an archived employer takes its opportunities with it
            qs = qs.filter(employer__archived_at__isnull=True)
        if q := g.get("q", "").strip():
            qs = qs.filter(title__icontains=q)
        if g.get("status") in {s for s, _ in Opportunity.STATUSES}:
            qs = qs.filter(status=g["status"])
        if g.get("kind") in {k for k, _ in Opportunity.TYPES}:
            qs = qs.filter(kind=g["kind"])
        try:
            if g.get("employer"):
                qs = qs.filter(employer_id=uuid.UUID(g["employer"]))
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            raise serializers.ValidationError({"filter": ["Invalid filter value."]}) from None
        size = page_size_of(g)
        return Response(
            {
                "total": qs.count(),
                "page_size": size,
                "results": [_opp_summary(o) for o in qs[offset : offset + size]],
            }
        )

    @extend_schema(request=OpportunityCreateSerializer, responses={201: dict, 409: dict})
    def post(self, request):
        s = OpportunityCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        employer = _get(data.pop("employer_id"))
        if employer.archived_at is not None:
            raise serializers.ValidationError(
                {"employer_id": "This employer is archived. Restore it first."}
            )
        try:
            o = services.create_opportunity(actor=request.user, employer=employer, data=data)
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_opp_detail(_opp(o.pk)), status=status.HTTP_201_CREATED)


class OpportunityDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "PATCH": EDIT, "DELETE": ARCHIVE}

    @extend_schema(operation_id="opportunities_detail", responses={200: dict})
    def get(self, request, pk):
        return Response(_opp_detail(_opp(pk)))

    @extend_schema(operation_id="opportunities_archive", responses={200: dict})
    def delete(self, request, pk):
        """Archive (soft delete). Restore with POST /opportunities/restore."""
        return Response(_archive_one(request, Opportunity.objects.all(), pk, "opportunity"))

    @extend_schema(request=OpportunitySerializer, responses={200: dict, 409: dict})
    def patch(self, request, pk):
        s = OpportunitySerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        try:
            services.update_opportunity(
                actor=request.user, opportunity=_opp(pk), data=dict(s.validated_data)
            )
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_opp_detail(_opp(pk)))


class OpportunityTransitionView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT}

    @extend_schema(request=TransitionSerializer, responses={200: dict, 409: dict})
    def post(self, request, pk):
        s = TransitionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.transition(
                actor=request.user,
                opportunity=_opp(pk),
                to=s.validated_data["to"],
                reason=s.validated_data.get("reason", ""),
            )
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_opp_detail(_opp(pk)))


class OpportunityHistoryView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(
        operation_id="opportunities_history", responses={200: dict(type="array", items={})}
    )
    def get(self, request, pk):
        return Response(services.opportunity_history(_opp(pk)))


class RequirementListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT}

    @extend_schema(request=RequirementSerializer, responses={201: dict, 409: dict})
    def post(self, request, pk):
        o = _opp(pk)
        s = RequirementSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            r = services.save_requirement(actor=request.user, opportunity=o, data=s.validated_data)
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_req(r), status=status.HTTP_201_CREATED)


class RequirementDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"PATCH": EDIT, "DELETE": EDIT}

    def _find(self, pk, rpk):
        o = _opp(pk)
        try:
            return o, o.requirements.get(pk=rpk)
        except OpportunityRequirement.DoesNotExist:
            raise NotFound from None

    @extend_schema(request=RequirementSerializer, responses={200: dict, 409: dict})
    def patch(self, request, pk, rpk):
        o, r = self._find(pk, rpk)
        s = RequirementSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        try:
            r = services.save_requirement(
                actor=request.user, opportunity=o, data=s.validated_data, requirement=r
            )
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_req(r))

    @extend_schema(responses={204: None, 409: dict})
    def delete(self, request, pk, rpk):
        o, r = self._find(pk, rpk)
        try:
            services.remove_requirement(actor=request.user, opportunity=o, requirement=r)
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)
