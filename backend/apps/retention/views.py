"""Data retention API (T-073). retention.view reads the rules and runs; retention.manage sets
periods, approves, revokes and runs the job."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission

from . import services

VIEW, MANAGE = "retention.view", "retention.manage"


def _error(exc):
    code = 404 if exc.code == "not_found" else status.HTTP_409_CONFLICT
    return Response(
        {"errors": [{"field": exc.field, "message": exc.message, "code": exc.code}]}, status=code
    )


class PeriodSerializer(serializers.Serializer):
    period_days = serializers.IntegerField(allow_null=True, min_value=1, max_value=36500)
    basis = serializers.CharField(allow_blank=True, max_length=2000, required=False, default="")


class RetentionReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class RunSerializer(serializers.Serializer):
    apply = serializers.BooleanField(default=False)
    confirm = serializers.BooleanField(default=False)


class RetentionView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="retention_overview", responses={200: dict})
    def get(self, request):
        return Response(services.overview())


class RetentionRunView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": MANAGE}

    @extend_schema(
        operation_id="retention_run", request=RunSerializer, responses={200: dict, 409: dict}
    )
    def post(self, request):
        s = RunSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if s.validated_data["apply"] and not s.validated_data["confirm"]:
            return Response(
                {"errors": [{"field": "confirm", "code": "confirm_required",
                             "message": "Confirm that this permanently clears the values."}]},
                status=status.HTTP_409_CONFLICT,
            )  # fmt: skip
        run = services.run(actor=request.user, apply=s.validated_data["apply"])
        return Response({**run, **services.overview()})


class RetentionClassView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"PUT": MANAGE}

    @extend_schema(
        operation_id="retention_set_period", request=PeriodSerializer,
        responses={200: dict, 409: dict},
    )  # fmt: skip
    def put(self, request, code):
        s = PeriodSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.set_period(actor=request.user, data_class=code, **s.validated_data)
        except services.RetentionError as exc:
            return _error(exc)
        return Response(services.overview())


class RetentionApproveView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": MANAGE}

    @extend_schema(operation_id="retention_approve", request=None, responses={200: dict})
    def post(self, request, code):
        try:
            services.approve(actor=request.user, data_class=code)
        except services.RetentionError as exc:
            return _error(exc)
        return Response(services.overview())


class RetentionRevokeView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": MANAGE}

    @extend_schema(
        operation_id="retention_revoke", request=RetentionReasonSerializer, responses={200: dict}
    )
    def post(self, request, code):
        s = RetentionReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.revoke(actor=request.user, data_class=code, **s.validated_data)
        except services.RetentionError as exc:
            return _error(exc)
        return Response(services.overview())
