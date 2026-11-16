"""Employer portal: the people PI staff have referred to a company, and what the company decides.

The company is found from the signed-in user, never from the request. Staff notes, scores and
other companies' referrals are not here (see ``referrals.own``); the candidate's phone and email
appear only once the company has selected them."""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission
from apps.api.downloads import pdf_response, photo_response
from apps.api.pagination import page_size_of
from apps.referrals import services as referrals

from . import services
from .data_views import company, violation

VIEW, RESPOND = "employer.view_referrals", "employer.respond_referrals"


def _run(fn, request, pk, **kwargs):
    """Run a referrals service for this company. Missing -> 404; a broken rule -> 409."""
    eid = company(request)
    try:
        return fn(
            actor=request.user, employer_id=eid, pk=pk, people=services.people(eid), **kwargs
        ), None
    except referrals.Missing:
        raise NotFound from None
    except referrals.RuleViolation as exc:
        return None, violation(exc)


class OwnReferralListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(
        operation_id="employer_referrals_list",
        parameters=[
            OpenApiParameter(n, str) for n in ("q", "stage", "opportunity", "offset", "page_size")
        ],
        responses={200: dict},
    )
    def get(self, request):
        g = request.query_params
        try:
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            raise serializers.ValidationError({"offset": ["Invalid value."]}) from None
        return Response(
            referrals.own_referrals(
                company(request),
                stage=g.get("stage", ""),
                q=g.get("q", ""),
                opportunity=g.get("opportunity", ""),
                view=g.get("view", ""),
                offset=offset,
                size=page_size_of(g),
            )
        )


class OwnReferralView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="employer_referrals_get", responses={200: dict})
    def get(self, request, pk):
        eid = company(request)
        try:
            return Response(referrals.own_referral(eid, pk, people=services.people(eid)))
        except referrals.Missing:
            raise NotFound from None


class OwnReferralReasonsView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="employer_referral_reasons", responses={200: dict})
    def get(self, request):
        company(request)
        return Response({"results": referrals.own_reasons()})


class OwnReferralMoveSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=referrals.EMPLOYER_MOVES)
    reason_id = serializers.UUIDField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class OwnInterviewSerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    place = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")
    note = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class OwnReferralMoveView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": RESPOND}

    @extend_schema(
        operation_id="employer_referrals_move",
        request=OwnReferralMoveSerializer,
        responses={200: dict, 409: dict},
    )
    def post(self, request, pk):
        s = OwnReferralMoveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        out, bad = _run(referrals.move_own_referral, request, pk, **s.validated_data)
        return bad or Response(out)


class OwnReferralInterviewView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": RESPOND}

    @extend_schema(
        operation_id="employer_referrals_interview",
        request=OwnInterviewSerializer,
        responses={200: dict, 409: dict},
    )
    def post(self, request, pk):
        s = OwnInterviewSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        out, bad = _run(referrals.set_own_interview, request, pk, **s.validated_data)
        return bad or Response(out)


class OwnReferralCvView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="employer_referrals_cv", responses={200: dict})
    def get(self, request, pk):
        eid = company(request)
        try:
            return Response(referrals.own_cv(eid, pk))
        except referrals.Missing:
            raise NotFound from None


class OwnReferralCvPdfView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="employer_referrals_cv_pdf", responses={200: bytes})
    def get(self, request, pk):
        eid = company(request)
        try:
            data, name = referrals.own_cv_pdf(actor=request.user, employer_id=eid, pk=pk)
        except referrals.Missing:
            raise NotFound from None
        return pdf_response(data, name)


class OwnReferralPhotoView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="employer_referrals_photo", responses={200: bytes})
    def get(self, request, pk):
        eid = company(request)
        try:
            return photo_response(referrals.own_photo(eid, pk))
        except referrals.Missing:
            raise NotFound from None
