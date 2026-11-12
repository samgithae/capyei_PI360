"""Youth portal API. Staff invite from a participant's page; the youth uses /youth/*."""

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.api import access
from apps.api.access import HasPermission
from apps.participants import services as participants

from . import services

INVITE, CONTACT = "participants.invite", "participants.view_contact"


def _fail(exc):
    raise serializers.ValidationError({exc.field: [exc.message]}) from exc


def _participant(request, pk):
    p = participants.find_active(pk) if participants.is_visible(request.user, pk) else None
    if p is None:
        raise NotFound
    return p


class InviteSerializer(serializers.Serializer):
    email = serializers.EmailField()


class InviteView(APIView):
    """Staff: invite status, send (or resend) and withdraw. Needs participants.invite."""

    permission_classes = [HasPermission]
    required_permission = {"GET": INVITE, "POST": INVITE, "DELETE": INVITE}

    def _status(self, request, p):
        can_see = access.has_permission(request.user, CONTACT)
        return {
            **services.invite_status(p),
            "emails": participants.email_addresses(p) if can_see else [],
        }

    @extend_schema(operation_id="participants_invite_get", responses={200: dict})
    def get(self, request, pk):
        return Response(self._status(request, _participant(request, pk)))

    @extend_schema(
        operation_id="participants_invite_send", request=InviteSerializer, responses={200: dict}
    )
    def post(self, request, pk):
        p = _participant(request, pk)
        s = InviteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if not access.has_permission(request.user, CONTACT):
            raise PermissionDenied
        try:
            services.send_invite(actor=request.user, participant=p, email=s.validated_data["email"])
        except services.PortalError as exc:
            _fail(exc)
        return Response(self._status(request, p))

    @extend_schema(operation_id="participants_invite_withdraw", responses={200: dict})
    def delete(self, request, pk):
        p = _participant(request, pk)
        try:
            services.withdraw_invite(actor=request.user, participant=p)
        except services.PortalError as exc:
            _fail(exc)
        return Response(self._status(request, p))


class _Public(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @method_decorator(csrf_protect)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)


class ActivateSerializer(TokenSerializer):
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class ActivateCheckView(_Public):
    @extend_schema(
        operation_id="youth_activate_check", request=TokenSerializer, responses={204: None}
    )
    def post(self, request):
        s = TokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.check_invite(s.validated_data["token"])
        except services.PortalError as exc:
            _fail(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivateView(_Public):
    @extend_schema(operation_id="youth_activate", request=ActivateSerializer, responses={204: None})
    def post(self, request):
        s = ActivateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.activate(**s.validated_data)
        except services.PortalError as exc:
            _fail(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)  # they then sign in as usual


class ConsentSerializer(serializers.Serializer):
    version = serializers.CharField(max_length=20)


class _Youth(APIView):
    permission_classes = [HasPermission]
    required_permission = "youth.self_service"

    def run(self, fn, **kwargs):
        try:
            return Response(fn(user=self.request.user, **kwargs))
        except services.PortalError as exc:
            if exc.field == "account":
                raise NotFound from exc
            _fail(exc)


class YouthMeView(_Youth):
    @extend_schema(operation_id="youth_me_get", responses={200: dict})
    def get(self, request):
        return self.run(services.read)


class YouthConsentView(_Youth):
    @extend_schema(operation_id="youth_consent", request=ConsentSerializer, responses={200: dict})
    def post(self, request):
        s = ConsentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self.run(services.give_consent, version=s.validated_data["version"])


class YouthProfileView(_Youth):
    @extend_schema(operation_id="youth_profile_put", request=dict, responses={200: dict})
    def put(self, request):
        s = participants.profile_serializer()(data=request.data)
        s.is_valid(raise_exception=True)
        return self.run(services.write_profile, data=s.validated_data)
