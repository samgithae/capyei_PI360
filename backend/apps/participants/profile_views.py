"""Capability profile API: read and edit what a youth can do, and let staff verify entries."""

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission
from apps.configuration.services import ConfigError

from . import capability_import, profile
from .models import Participant, ParticipantSkill

PROFILE, EDIT = "participants.view_profile", "participants.edit"


class _Qualification(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    level_id = serializers.UUIDField()
    title = serializers.CharField(max_length=200, allow_blank=True, required=False)
    institution = serializers.CharField(max_length=200, allow_blank=True, required=False)
    grade = serializers.CharField(max_length=60, allow_blank=True, required=False)
    year_awarded = serializers.IntegerField(
        min_value=1950, max_value=2100, allow_null=True, required=False
    )


class _Skill(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    skill_id = serializers.UUIDField()
    proficiency = serializers.ChoiceField(
        choices=[c for c, _ in ParticipantSkill.PROFICIENCY], required=False
    )


class _Experience(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    role_title = serializers.CharField(max_length=200)
    employer_name = serializers.CharField(max_length=200, allow_blank=True, required=False)
    sector_id = serializers.UUIDField(allow_null=True, required=False)
    months = serializers.IntegerField(min_value=0, max_value=720)


class _Readiness(serializers.Serializer):
    available_from = serializers.DateField(allow_null=True, required=False)
    work_patterns = serializers.ListField(
        child=serializers.CharField(max_length=20), max_length=10, required=False
    )
    interest_sector_ids = serializers.ListField(
        child=serializers.UUIDField(), max_length=30, required=False
    )


class ProfileSerializer(serializers.Serializer):
    qualifications = _Qualification(many=True, max_length=30, required=False)
    skills = _Skill(many=True, max_length=60, required=False)
    experience = _Experience(many=True, max_length=40, required=False)
    readiness = _Readiness(required=False)


class VerifySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=sorted(profile.KINDS))
    id = serializers.UUIDField()
    verified = serializers.BooleanField(default=True)


def _participant(request, pk):
    try:
        return Participant.objects.visible_to(request.user, archived=None).get(pk=pk)
    except Participant.DoesNotExist:
        raise NotFound from None


def _fail(exc):
    raise serializers.ValidationError({exc.field: [str(exc)]}) from exc


class ProfileView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PROFILE, "PUT": EDIT}

    @extend_schema(operation_id="participants_profile_get", responses={200: dict})
    def get(self, request, pk):
        return Response({**profile.read(_participant(request, pk)), "options": profile.options()})

    @extend_schema(
        operation_id="participants_profile_put", request=ProfileSerializer, responses={200: dict}
    )
    def put(self, request, pk):
        p = _participant(request, pk)
        s = ProfileSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            profile.write(actor=request.user, p=p, data=s.validated_data)
            return Response({**profile.read(p), "options": profile.options()})
        except profile.ProfileError as exc:
            _fail(exc)


class ProfileOptionsView(APIView):
    """What the capability form may choose from, before any youth exists (Add youth)."""

    permission_classes = [HasPermission]
    required_permission = {"GET": EDIT}

    @extend_schema(operation_id="participants_profile_options", responses={200: dict})
    def get(self, request):
        return Response(profile.options())


class ProfileVerifyView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT}

    @extend_schema(
        operation_id="participants_profile_verify",
        request=VerifySerializer,
        responses={200: dict},
    )
    def post(self, request, pk):
        p = _participant(request, pk)
        s = VerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            return Response(
                profile.verify(
                    actor=request.user, p=p, kind=d["kind"], fact_id=d["id"], verified=d["verified"]
                )
            )
        except profile.ProfileError as exc:
            _fail(exc)


class ProfileImportView(APIView):
    """Upload a CSV or Excel file of capability facts. ``dry_run=1`` previews without saving."""

    permission_classes = [HasPermission]
    required_permission = {"POST": EDIT}
    parser_classes = [MultiPartParser]

    @extend_schema(
        operation_id="participants_profile_import",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "binary"},
                    "dry_run": {"type": "boolean"},
                },
            }
        },
        responses={200: dict},
    )
    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise serializers.ValidationError({"file": "Choose a CSV or Excel file."})
        dry = str(request.data.get("dry_run", "")).lower() in ("1", "true", "yes")
        try:
            result = capability_import.run_import(
                actor=request.user, filename=upload.name, content=upload.read(), dry_run=dry
            )
        except ConfigError as exc:
            raise serializers.ValidationError({exc.field: exc.message}) from exc
        return Response(result)


class ProfileImportTemplateView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": EDIT}

    @extend_schema(operation_id="participants_profile_import_template", responses={200: bytes})
    def get(self, request):
        resp = HttpResponse(capability_import.template_csv(), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="youth-capability-template.csv"'
        return resp
