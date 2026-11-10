"""Employer API (T-044, FR-11). employers.view reads, employers.edit changes."""

import uuid

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission
from apps.configuration import services as configuration

from . import services
from .models import Employer, EmployerContact

VIEW, EDIT = "employers.view", "employers.edit"
PAGE = 50


def _summary(e):
    return {
        "id": str(e.pk),
        "name": e.name,
        "status": e.status,
        "sector": e.sector.name if e.sector_id else "",
        "county": e.county.name if e.county_id else "",
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
            OpenApiParameter(n, str) for n in ("q", "status", "sector", "county", "offset")
        ],
        responses={200: dict},
    )
    def get(self, request):
        qs, g = Employer.objects.select_related("sector", "county"), request.query_params
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
        try:
            offset = max(int(g.get("offset", 0)), 0)
        except ValueError:
            offset = 0
        return Response(
            {
                "total": qs.count(),
                "page_size": PAGE,
                "results": [_summary(e) for e in qs[offset : offset + PAGE]],
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
    required_permission = {"GET": VIEW, "PATCH": EDIT}

    @extend_schema(operation_id="employers_detail", responses={200: dict})
    def get(self, request, pk):
        return Response(_detail(_get(pk)))

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
