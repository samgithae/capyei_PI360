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

_refs, _contact, _req = services.refs, services.contact_dict, services.requirement_dict
_opp_summary, _opp_detail = services.opportunity_summary, services.opportunity_detail


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
        "sectors": _refs(e.sectors.all()),
        "counties": _refs(e.counties.all()),
        "archived": e.archived_at is not None,
    }


def _detail(e):
    return {
        **_summary(e),
        "sector_ids": [s["id"] for s in _refs(e.sectors.all())],
        "county_ids": [c["id"] for c in _refs(e.counties.all())],
        "sub_county": e.sub_county,
        "address": e.address,
        "website": e.website,
        "notes": e.notes,
        "contacts": [_contact(c) for c in e.contacts.all()],
    }


class IdList(serializers.ListField):
    """A list of reference ids (counties, sectors). Duplicates are dropped by the services."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(child=serializers.UUIDField(), allow_empty=True, max_length=100, **kwargs)


class EmployerSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    sector_ids = IdList()
    county_ids = IdList()
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
        return Employer.objects.prefetch_related("sectors", "counties").get(pk=pk)
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
    except (services.DuplicateWarning, services.RuleViolation) as exc:
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
        qs = archived_filter(Employer.objects.prefetch_related("sectors", "counties"), g)
        if q := g.get("q", "").strip():
            qs = qs.filter(name_normalised__contains=services.norm(q))
        if g.get("status") in {s for s, _ in Employer.STATUSES}:
            qs = qs.filter(status=g["status"])
        try:
            if g.get("sector"):
                qs = qs.filter(sectors__id=uuid.UUID(g["sector"]))
            if g.get("county"):
                qs = qs.filter(counties__id=uuid.UUID(g["county"]))
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
        if isinstance(result, services.RuleViolation):
            return _violation(result)
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
        if isinstance(result, services.RuleViolation):
            return _violation(result)
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


def _opp(pk):
    try:
        return (
            Opportunity.objects.select_related("employer")
            .prefetch_related("sectors", "counties")
            .get(pk=pk)
        )
    except Opportunity.DoesNotExist:
        raise NotFound from None


class OpportunitySerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    kind = serializers.ChoiceField(choices=Opportunity.TYPES, required=False)
    sector_ids = IdList()
    county_ids = IdList()
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)
    positions = serializers.IntegerField(min_value=1, max_value=10000, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    start_date = serializers.DateField(required=False, allow_null=True)
    closing_date = serializers.DateField(required=False, allow_null=True)


class OpportunityCreateSerializer(OpportunitySerializer):
    employer_id = serializers.UUIDField()


class OpportunityUpdateSerializer(OpportunitySerializer):
    """Moving a draft to another employer is allowed; the services re-check counties and sectors."""

    employer_id = serializers.UUIDField(required=False)


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
            for n in (
                "q",
                "status",
                "employer",
                "kind",
                "awaiting",
                "archived",
                "offset",
                "page_size",
            )
        ],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        qs = archived_filter(
            Opportunity.objects.select_related("employer").prefetch_related("counties", "sectors"),
            g,
        )
        if g.get("archived") != "1":  # an archived employer takes its opportunities with it
            qs = qs.filter(employer__archived_at__isnull=True)
        if q := g.get("q", "").strip():
            qs = qs.filter(title__icontains=q)
        if g.get("status") in {s for s, _ in Opportunity.STATUSES}:
            qs = qs.filter(status=g["status"])
        if g.get("kind") in {k for k, _ in Opportunity.TYPES}:
            qs = qs.filter(kind=g["kind"])
        if g.get("awaiting") == "1":  # companies asking PI staff to publish
            qs = qs.filter(publish_requested_at__isnull=False)
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

    @extend_schema(request=OpportunityUpdateSerializer, responses={200: dict, 409: dict})
    def patch(self, request, pk):
        s = OpportunityUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        if "employer_id" in data:
            data["employer"] = _get(data.pop("employer_id"))
        try:
            services.update_opportunity(actor=request.user, opportunity=_opp(pk), data=data)
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


class DeclineSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class OpportunityDeclineView(APIView):
    """Staff turn down a company's request to publish; the reason is shown to the company.
    Approving is the ordinary transition to open, which also clears the request."""

    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT}

    @extend_schema(
        operation_id="opportunities_publish_decline",
        request=DeclineSerializer,
        responses={200: dict, 409: dict},
    )
    def post(self, request, pk):
        s = DeclineSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.decline_publish(
                actor=request.user, opportunity=_opp(pk), reason=s.validated_data["reason"]
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


class SkillItemSerializer(serializers.Serializer):
    skill_id = serializers.UUIDField()
    is_mandatory = serializers.BooleanField(required=False, default=False)


class SkillSyncSerializer(serializers.Serializer):
    skills = SkillItemSerializer(many=True)


class SkillAddSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    category = serializers.CharField(max_length=80, required=False, allow_blank=True)
    confirm_similar = serializers.BooleanField(required=False, default=False)


class SkillSearchView(APIView):
    """Pick-list search: partial, any case, paged. ``category`` narrows to one group."""

    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str),
            OpenApiParameter("category", str),
            OpenApiParameter("limit", int),
            OpenApiParameter("offset", int),
        ],
        responses={200: dict},
    )
    def get(self, request):
        p = request.query_params

        def num(key, default):
            try:
                return int(p.get(key, default))
            except ValueError:
                return default

        total, rows = configuration.search_skills(
            q=p.get("q", ""), category=p.get("category", ""),
            limit=num("limit", 20), offset=num("offset", 0),
        )  # fmt: skip
        return Response({"total": total, "results": rows})


class SkillCategoryView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({"results": configuration.skill_categories()})


class SkillPopularView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({"results": services.popular_skills()})


class SkillAddView(APIView):
    """Add a missing skill to the central list from the picker (409 when it already exists)."""

    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT}

    @extend_schema(request=SkillAddSerializer, responses={201: dict, 409: dict})
    def post(self, request):
        s = SkillAddSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            row = configuration.add_skill(actor=request.user, **s.validated_data)
        except configuration.SkillConflict as exc:
            return Response(
                {
                    "errors": [{"field": "name", "message": exc.message, "code": exc.code}],
                    "existing": exc.existing,
                    "similar": exc.similar,
                },
                status=status.HTTP_409_CONFLICT,
            )
        except configuration.ConfigError as exc:
            return Response(
                {"errors": [{"field": exc.field, "message": exc.message, "code": "invalid"}]},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(row, status=status.HTTP_201_CREATED)


class RequirementSkillsView(APIView):
    """Save the whole skills picker in one call (add, remove and must-have flags together)."""

    permission_classes = [HasPermission]
    required_permission = {"PUT": EDIT}

    @extend_schema(request=SkillSyncSerializer, responses={200: dict, 409: dict})
    def put(self, request, pk):
        o = _opp(pk)
        s = SkillSyncSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            rows = services.sync_skill_requirements(
                actor=request.user, opportunity=o, items=s.validated_data["skills"]
            )
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response({"requirements": [_req(r) for r in rows]})


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
