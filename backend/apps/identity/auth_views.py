"""Staff sign-in, MFA, sign-out and password flows (T-034; FR-01, SEC-10, SEC-11).

CSRF: DRF views are csrf_exempt and only enforce CSRF for signed-in users, so the sign-in
POSTs apply csrf_protect themselves. The SPA gets its cookie from GET /me (ADR-023).
"""

import time

from django.conf import settings
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth import password_validation as pv
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit import services as audit

from . import lockout, mfa
from .middleware import STARTED
from .serializers import (
    LoginResultSerializer,
    LoginSerializer,
    MfaCodeSerializer,
    MfaSetupSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)

User = get_user_model()
BACKEND = "django.contrib.auth.backends.ModelBackend"
PENDING_USER = "mfa_pending_user"
PENDING_AT = "mfa_pending_at"
PENDING_TRIES = "mfa_pending_tries"
MAX_MFA_TRIES = 5


class InvalidCredentials(exceptions.APIException):
    status_code = 401
    default_detail = "Incorrect username or password."
    default_code = "invalid_credentials"


class InvalidCode(exceptions.APIException):
    status_code = 401
    default_detail = "That code is not valid."
    default_code = "invalid_mfa_code"


class Locked(exceptions.Throttled):
    default_detail = "Too many failed attempts. Try again later."
    default_code = "account_locked"


class MfaNotPending(exceptions.APIException):
    status_code = 409
    default_detail = "Sign in with your password first."
    default_code = "mfa_not_pending"


class _AuthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @method_decorator(csrf_protect)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


def _finish_login(request, user):
    login(request, user, backend=BACKEND)
    request.session[STARTED] = time.time()
    for key in (PENDING_USER, PENDING_AT, PENDING_TRIES):
        request.session.pop(key, None)
    lockout.clear(user.get_username())
    audit.record(
        actor=user,
        action="auth.login",
        object_type="user",
        object_id=user.pk,
        after={"mfa": mfa.required_for(user)},
    )


def _pending_user(request):
    uid = request.session.get(PENDING_USER)
    at = request.session.get(PENDING_AT, 0)
    if not uid or time.time() - at > settings.AUTH_MFA_PENDING_SECONDS:
        raise MfaNotPending
    user = User.objects.filter(pk=uid, is_active=True).first()
    if user is None:
        raise MfaNotPending
    return user


def _mfa_failed(request, user):
    tries = request.session.get(PENDING_TRIES, 0) + 1
    request.session[PENDING_TRIES] = tries
    audit.record(actor=user, action="auth.mfa_failed", object_type="user", object_id=user.pk)
    if tries >= MAX_MFA_TRIES:
        for key in (PENDING_USER, PENDING_AT, PENDING_TRIES):
            request.session.pop(key, None)
    raise InvalidCode


class LoginView(_AuthView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses=LoginResultSerializer)
    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        username = data.validated_data["username"]
        remaining = lockout.locked_seconds(username)
        if remaining:
            raise Locked(wait=remaining)
        user = authenticate(request, username=username, password=data.validated_data["password"])
        if user is None:
            known = User.objects.filter(username__iexact=username).first()
            audit.record(
                actor=None,
                action="auth.login_failed",
                object_type="user",
                # The attempted name is not stored: a mistyped password often lands here.
                object_id=known.pk if known else "unknown",
            )
            if lockout.register_failure(username):
                audit.record(
                    actor=None,
                    action="auth.lockout",
                    object_type="user",
                    object_id=known.pk if known else "unknown",
                )
            raise InvalidCredentials
        if mfa.required_for(user):
            request.session.cycle_key()
            request.session[PENDING_USER] = user.pk
            request.session[PENDING_AT] = time.time()
            request.session[PENDING_TRIES] = 0
            return Response(
                {"status": "mfa_required", "mfa_enrolled": mfa.confirmed_device(user) is not None}
            )
        _finish_login(request, user)
        return Response({"status": "ok"})


class MfaSetupView(_AuthView):
    """First-time enrolment: returns the otpauth URL to show as a QR code."""

    @extend_schema(request=None, responses=MfaSetupSerializer)
    def post(self, request):
        user = _pending_user(request)
        if mfa.confirmed_device(user):
            raise exceptions.PermissionDenied("MFA is already set up for this account.")
        device = mfa.start_enrolment(user)
        return Response({"config_url": device.config_url})


class MfaConfirmView(_AuthView):
    @extend_schema(request=MfaCodeSerializer, responses=LoginResultSerializer)
    def post(self, request):
        user = _pending_user(request)
        code = MfaCodeSerializer(data=request.data)
        code.is_valid(raise_exception=True)
        device = mfa.pending_device(user)
        if device is None or mfa.confirmed_device(user):
            raise MfaNotPending
        if not device.verify_token(code.validated_data["code"]):
            _mfa_failed(request, user)
        device.confirmed = True
        device.save(update_fields=["confirmed"])
        audit.record(actor=user, action="auth.mfa_enrolled", object_type="user", object_id=user.pk)
        _finish_login(request, user)
        return Response({"status": "ok"})


class MfaVerifyView(_AuthView):
    @extend_schema(request=MfaCodeSerializer, responses=LoginResultSerializer)
    def post(self, request):
        user = _pending_user(request)
        code = MfaCodeSerializer(data=request.data)
        code.is_valid(raise_exception=True)
        device = mfa.confirmed_device(user)
        if device is None:
            raise MfaNotPending
        if not device.verify_token(code.validated_data["code"]):
            _mfa_failed(request, user)
        _finish_login(request, user)
        return Response({"status": "ok"})


class LogoutView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        user = request.user
        if user.is_authenticated:
            audit.record(actor=user, action="auth.logout", object_type="user", object_id=user.pk)
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _validate_new_password(user, password):
    try:
        pv.validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"new_password": list(exc.messages)}) from exc


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, responses={204: None})
    def post(self, request):
        data = PasswordChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(data.validated_data["current_password"]):
            raise serializers.ValidationError({"current_password": ["Incorrect password."]})
        _validate_new_password(user, data.validated_data["new_password"])
        user.set_password(data.validated_data["new_password"])
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)
        audit.record(
            actor=user, action="auth.password_changed", object_type="user", object_id=user.pk
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(_AuthView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=PasswordResetRequestSerializer, responses={202: None})
    def post(self, request):
        data = PasswordResetRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        email = data.validated_data["email"]
        for user in User.objects.filter(email__iexact=email, is_active=True):
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?uid={uid}&token={token}"
            mail.send_mail(
                "Reset your CAP-YEI PI 360 password",
                f"Use this link to choose a new password. It expires in "
                f"{settings.PASSWORD_RESET_TIMEOUT // 60} minutes.\n\n{link}\n\n"
                "If you did not ask for this, ignore this message.",
                None,
                [user.email],
            )
            audit.record(
                actor=None,
                action="auth.password_reset_requested",
                object_type="user",
                object_id=user.pk,
            )
        # Same answer whether or not the address is known (no account enumeration).
        return Response(status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(_AuthView):
    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None})
    def post(self, request):
        data = PasswordResetConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        bad = serializers.ValidationError({"token": ["This reset link is invalid or has expired."]})
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(data.validated_data["uid"])))
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            raise bad from None
        if not user.is_active or not default_token_generator.check_token(
            user, data.validated_data["token"]
        ):
            raise bad
        _validate_new_password(user, data.validated_data["new_password"])
        user.set_password(data.validated_data["new_password"])
        user.save(update_fields=["password"])  # also invalidates the token and old sessions
        lockout.clear(user.get_username())
        audit.record(
            actor=user, action="auth.password_reset", object_type="user", object_id=user.pk
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
