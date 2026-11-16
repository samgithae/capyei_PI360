"""Employer portal: a company's own profile, contacts and opportunities.

Every view finds the company from the signed-in user (``services.own_employer_id``), never from
an id in the request, and the employer services limit each query to that company: an id that
belongs to anyone else is a 404. Staff notes and other companies' data are never returned."""

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission
from apps.api.downloads import logo_response, read_logo_upload
from apps.api.pagination import page_size_of
from apps.configuration import services as configuration
from apps.employers import services as employers

from . import services

VIEW_PROFILE, EDIT_PROFILE = "employer.view_profile", "employer.edit_profile"
VIEW_OPP, EDIT_OPP, PUBLISH = (
    "employer.view_opportunities", "employer.edit_opportunities", "employer.publish_opportunities"
)  # fmt: skip


def company(request):
    """The id of the signed-in user's company; 404 when the account is not linked or is off."""
    try:
        return services.own_employer_id(request.user)
    except services.PortalError as exc:
        raise NotFound from exc


def violation(exc):
    return Response(
        {"errors": [{"field": exc.field, "message": exc.message, "code": exc.code}]},
        status=status.HTTP_409_CONFLICT,
    )


def scoped(fn, request, **kwargs):
    """Run an employer service for this user's company. Missing -> 404; a broken rule -> 409.
    Returns ``(result, None)`` or ``(None, response)``."""
    try:
        return fn(actor=request.user, employer_id=company(request), **kwargs), None
    except employers.Missing:
        raise NotFound from None
    except employers.RuleViolation as exc:
        return None, violation(exc)


class IdList(serializers.ListField):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(child=serializers.UUIDField(), allow_empty=True, max_length=100, **kwargs)


# ---- profile and contacts ---------------------------------------------------------------------


class OwnProfileSerializer(serializers.Serializer):
    """The name, status and notes are PI staff's; a company edits where and what it does."""

    sub_county = serializers.CharField(max_length=100, required=False, allow_blank=True)
    address = serializers.CharField(max_length=200, required=False, allow_blank=True)
    website = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(max_length=600, required=False, allow_blank=True)
    sector_ids = IdList()
    county_ids = IdList()


class OwnContactSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    role = serializers.CharField(max_length=100, required=False, allow_blank=True)
    email = serializers.EmailField(max_length=200, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    is_primary = serializers.BooleanField(required=False, default=False)


class OwnProfileView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW_PROFILE, "PATCH": EDIT_PROFILE}

    @extend_schema(operation_id="employer_profile_get", responses={200: dict})
    def get(self, request):
        out, bad = scoped(lambda **k: employers.own_profile(k["employer_id"]), request)
        return bad or Response(out)

    @extend_schema(
        operation_id="employer_profile_patch",
        request=OwnProfileSerializer,
        responses={200: dict, 409: dict},
    )
    def patch(self, request):
        s = OwnProfileSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        out, bad = scoped(employers.update_own_profile, request, data=dict(s.validated_data))
        return bad or Response(out)


class OwnLogoView(APIView):
    """The company's logo. Any signed-in member who can see the profile may see it; changing or
    removing it needs the same permission as editing the profile."""

    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW_PROFILE, "POST": EDIT_PROFILE, "DELETE": EDIT_PROFILE}
    parser_classes = [MultiPartParser]

    @extend_schema(operation_id="employer_logo_get", responses={200: bytes})
    def get(self, request):
        eid = company(request)
        try:
            return logo_response(employers.own_logo(eid))
        except employers.Missing:
            raise NotFound from None

    @extend_schema(
        operation_id="employer_logo_post",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"logo": {"type": "string", "format": "binary"}},
            }
        },
        responses={200: dict},
    )
    def post(self, request):
        raw = read_logo_upload(request)
        try:
            out, bad = scoped(employers.save_own_logo, request, raw=raw)
        except employers.LogoError as exc:
            raise serializers.ValidationError({exc.field: [str(exc)]}) from exc
        return bad or Response(out)

    @extend_schema(operation_id="employer_logo_delete", responses={200: dict})
    def delete(self, request):
        out, bad = scoped(employers.remove_own_logo, request)
        return bad or Response(out)


class OwnContactListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT_PROFILE}

    @extend_schema(
        operation_id="employer_contacts_post",
        request=OwnContactSerializer,
        responses={201: dict, 409: dict},
    )
    def post(self, request):
        s = OwnContactSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        out, bad = scoped(employers.save_own_contact, request, data=dict(s.validated_data))
        return bad or Response(out, status=status.HTTP_201_CREATED)


class OwnContactView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"PATCH": EDIT_PROFILE, "DELETE": EDIT_PROFILE}

    @extend_schema(
        operation_id="employer_contacts_patch",
        request=OwnContactSerializer,
        responses={200: dict, 409: dict},
    )
    def patch(self, request, cpk):
        s = OwnContactSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        out, bad = scoped(
            employers.save_own_contact, request, data=dict(s.validated_data), contact_id=cpk
        )
        return bad or Response(out)

    @extend_schema(operation_id="employer_contacts_delete", responses={204: None})
    def delete(self, request, cpk):
        _, bad = scoped(employers.remove_own_contact, request, contact_id=cpk)
        return bad or Response(status=status.HTTP_204_NO_CONTENT)


# ---- opportunities ----------------------------------------------------------------------------


class OwnOpportunitySerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    kind = serializers.ChoiceField(choices=employers.KIND_CHOICES, required=False)
    sector_ids = IdList()
    county_ids = IdList()
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)
    positions = serializers.IntegerField(min_value=1, max_value=10000, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    start_date = serializers.DateField(required=False, allow_null=True)
    closing_date = serializers.DateField(required=False, allow_null=True)


class OwnOpportunityMoveSerializer(serializers.Serializer):
    """``open`` publishes, or asks PI staff to when the company may not publish on its own;
    ``closed`` stops taking referrals; ``withdraw`` takes back a request that is waiting."""

    to = serializers.ChoiceField(choices=["open", "closed", "withdraw"])


class OwnRequirementSerializer(serializers.Serializer):
    factor = serializers.ChoiceField(choices=employers.FACTOR_CHOICES)
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


class OwnSkillItemSerializer(serializers.Serializer):
    skill_id = serializers.UUIDField()
    is_mandatory = serializers.BooleanField(required=False, default=False)


class OwnSkillSyncSerializer(serializers.Serializer):
    skills = OwnSkillItemSerializer(many=True)


def _with_rights(out, user):
    """Tell the screen what the company's switches allow, so it can word the button."""
    return {**out, "publishes_directly": services.publishes_directly(user)}


class OwnOpportunityListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW_OPP, "POST": EDIT_OPP}

    @extend_schema(
        operation_id="employer_opportunities_list",
        parameters=[OpenApiParameter(n, str) for n in ("q", "status", "offset", "page_size")],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        try:
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            raise serializers.ValidationError({"offset": ["Invalid value."]}) from None
        eid = company(request)
        return Response(
            employers.own_opportunities(
                eid,
                status=g.get("status", ""),
                q=g.get("q", ""),
                view=g.get("view", ""),
                offset=offset,
                size=page_size_of(g),
                today=timezone.localdate(),
            )
        )

    @extend_schema(
        operation_id="employer_opportunities_post",
        request=OwnOpportunitySerializer,
        responses={201: dict, 409: dict},
    )
    def post(self, request):
        s = OwnOpportunitySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        out, bad = scoped(employers.create_own_opportunity, request, data=dict(s.validated_data))
        return bad or Response(_with_rights(out, request.user), status=status.HTTP_201_CREATED)


class OwnOpportunityView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW_OPP, "PATCH": EDIT_OPP}

    @extend_schema(operation_id="employer_opportunities_get", responses={200: dict})
    def get(self, request, pk):
        try:
            out = employers.own_opportunity(company(request), pk)
        except employers.Missing:
            raise NotFound from None
        return Response(_with_rights(out, request.user))

    @extend_schema(
        operation_id="employer_opportunities_patch",
        request=OwnOpportunitySerializer,
        responses={200: dict, 409: dict},
    )
    def patch(self, request, pk):
        s = OwnOpportunitySerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        out, bad = scoped(
            employers.update_own_opportunity, request, pk=pk, data=dict(s.validated_data)
        )
        return bad or Response(_with_rights(out, request.user))


class OwnOpportunityMoveView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": PUBLISH}

    @extend_schema(
        operation_id="employer_opportunities_move",
        request=OwnOpportunityMoveSerializer,
        responses={200: dict, 409: dict},
    )
    def post(self, request, pk):
        s = OwnOpportunityMoveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        out, bad = scoped(
            employers.move_own_opportunity,
            request,
            pk=pk,
            to=s.validated_data["to"],
            publish_directly=services.publishes_directly(request.user),
            label=services.own_member(request.user).full_name,
        )
        return bad or Response(_with_rights(out, request.user))


class OwnRequirementListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT_OPP}

    @extend_schema(
        operation_id="employer_requirements_post",
        request=OwnRequirementSerializer,
        responses={201: dict, 409: dict},
    )
    def post(self, request, pk):
        s = OwnRequirementSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        out, bad = scoped(
            employers.save_own_requirement, request, pk=pk, data=dict(s.validated_data)
        )
        return bad or Response(out, status=status.HTTP_201_CREATED)


class OwnSkillSearchView(APIView):
    """The skills pick-list a company chooses requirements from: search, any case, paged. A
    company picks from the shared list; adding a new skill stays with PI staff."""

    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW_OPP}

    @extend_schema(
        operation_id="employer_skills_search",
        parameters=[
            OpenApiParameter("q", str),
            OpenApiParameter("category", str),
            OpenApiParameter("limit", int),
            OpenApiParameter("offset", int),
        ],
        responses={200: dict},
    )
    def get(self, request):
        company(request)
        p = request.query_params

        def num(key, default):
            try:
                return max(0, min(int(p.get(key, default)), 100))
            except ValueError:
                return default

        total, rows = configuration.search_skills(
            q=p.get("q", ""), category=p.get("category", ""),
            limit=num("limit", 20), offset=num("offset", 0),
        )  # fmt: skip
        return Response({"total": total, "results": rows})


class OwnSkillCategoryView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW_OPP}

    @extend_schema(operation_id="employer_skills_categories", responses={200: dict})
    def get(self, request):
        company(request)
        return Response({"results": configuration.skill_categories()})


class OwnSkillPopularView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW_OPP}

    @extend_schema(operation_id="employer_skills_popular", responses={200: dict})
    def get(self, request):
        company(request)
        return Response({"results": employers.popular_skills()})


class OwnRequirementSkillsView(APIView):
    """Save the whole skills picker in one call, like the staff screen."""

    permission_classes = [HasPermission]
    required_permission = {"PUT": EDIT_OPP}

    @extend_schema(
        operation_id="employer_requirement_skills_put",
        request=OwnSkillSyncSerializer,
        responses={200: dict, 409: dict},
    )
    def put(self, request, pk):
        s = OwnSkillSyncSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        out, bad = scoped(
            employers.sync_own_skills, request, pk=pk, items=s.validated_data["skills"]
        )
        return bad or Response(out)


class OwnRequirementView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"PATCH": EDIT_OPP, "DELETE": EDIT_OPP}

    @extend_schema(
        operation_id="employer_requirements_patch",
        request=OwnRequirementSerializer,
        responses={200: dict, 409: dict},
    )
    def patch(self, request, pk, rpk):
        s = OwnRequirementSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        out, bad = scoped(
            employers.save_own_requirement,
            request,
            pk=pk,
            data=dict(s.validated_data),
            requirement_id=rpk,
        )
        return bad or Response(out)

    @extend_schema(operation_id="employer_requirements_delete", responses={204: None, 409: dict})
    def delete(self, request, pk, rpk):
        _, bad = scoped(employers.remove_own_requirement, request, pk=pk, requirement_id=rpk)
        return bad or Response(status=status.HTTP_204_NO_CONTENT)


class OwnDashboardView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": "employer.view_dashboard"}

    @extend_schema(operation_id="employer_dashboard", responses={200: dict})
    def get(self, request):
        company(request)  # 404 when the account has no active company
        return Response(services.dashboard(request.user))
