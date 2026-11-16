"""Employer portal API. Staff set up the first account from the employer's page; a company's
own users use /employer/*. Every company-side view finds the company from the signed-in user."""

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.api.access import HasPermission
from apps.employers import services as employers

from . import services

VIEW, INVITE = "employers.view", "employers.invite_user"
PORTAL, MANAGE = services.PORTAL, services.MANAGE_STAFF


def _fail(exc):
    raise serializers.ValidationError({exc.field: [exc.message]}) from exc


def _run(fn, **kwargs):
    """Call a service; a missing record or company is a 404, any other refusal a 400."""
    try:
        return fn(**kwargs)
    except services.PortalError as exc:
        if exc.field == "account":
            raise NotFound from exc
        _fail(exc)


class EmployerInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    job_title = serializers.CharField(max_length=100, allow_blank=True, required=False)
    role_id = serializers.IntegerField()


class MemberPatchSerializer(serializers.Serializer):
    role_id = serializers.IntegerField(required=False)
    active = serializers.BooleanField(required=False)
    reason = serializers.CharField(max_length=300, allow_blank=True, required=False)

    def validate(self, attrs):
        if "role_id" not in attrs and "active" not in attrs:
            raise serializers.ValidationError("Change the role or switch the account on or off.")
        return attrs


def _patch(request, employer_id, mpk):
    s = MemberPatchSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    row = None
    if "role_id" in d:
        row = _run(
            services.change_role,
            actor=request.user,
            employer_id=employer_id,
            member_id=mpk,
            role_id=d["role_id"],
        )
    if "active" in d:
        row = _run(
            services.set_active,
            actor=request.user,
            employer_id=employer_id,
            member_id=mpk,
            active=d["active"],
            reason=d.get("reason", ""),
        )
    return Response(row)


def _remove(request, employer_id, mpk):
    _run(services.withdraw_invite, actor=request.user, employer_id=employer_id, member_id=mpk)
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---- public: activate -----------------------------------------------------------------------


class _Public(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @method_decorator(csrf_protect)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class EmployerTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)


class EmployerActivateSerializer(EmployerTokenSerializer):
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class ActivateCheckView(_Public):
    @extend_schema(
        operation_id="employer_activate_check",
        request=EmployerTokenSerializer,
        responses={204: None},
    )
    def post(self, request):
        s = EmployerTokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.check_invite(s.validated_data["token"])
        except services.PortalError as exc:
            _fail(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivateView(_Public):
    @extend_schema(
        operation_id="employer_activate", request=EmployerActivateSerializer, responses={204: None}
    )
    def post(self, request):
        s = EmployerActivateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.activate(**s.validated_data)
        except services.PortalError as exc:
            _fail(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)  # they then sign in as usual


# ---- company side ---------------------------------------------------------------------------


class EmployerMeView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PORTAL}

    @extend_schema(operation_id="employer_me_get", responses={200: dict})
    def get(self, request):
        return Response(_run(services.me, user=request.user))


class EmployerRolesView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": MANAGE}

    @extend_schema(operation_id="employer_roles_list", responses={200: dict(type="array")})
    def get(self, request):
        _run(services.own_member, user=request.user)
        return Response(
            [{k: r[k] for k in ("id", "name", "description")} for r in services.assignable_roles()]
        )


class EmployerStaffView(APIView):
    """A company admin's team: list, invite."""

    permission_classes = [HasPermission]
    required_permission = {"GET": MANAGE, "POST": MANAGE}

    @extend_schema(operation_id="employer_staff_list", responses={200: dict(type="array")})
    def get(self, request):
        member = _run(services.own_member, user=request.user)
        return Response(services.team(member.employer_id))

    @extend_schema(
        operation_id="employer_staff_invite",
        request=EmployerInviteSerializer,
        responses={201: dict},
    )
    def post(self, request):
        member = _run(services.own_member, user=request.user)
        s = EmployerInviteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        row = _run(
            services.invite, actor=request.user, employer_id=member.employer_id, **s.validated_data
        )
        return Response(row, status=status.HTTP_201_CREATED)


class EmployerStaffMemberView(APIView):
    """Change a colleague's role, switch them off or on, or withdraw an unaccepted invite."""

    permission_classes = [HasPermission]
    required_permission = {"PATCH": MANAGE, "DELETE": MANAGE}

    @extend_schema(
        operation_id="employer_staff_update", request=MemberPatchSerializer, responses={200: dict}
    )
    def patch(self, request, mpk):
        member = _run(services.own_member, user=request.user)
        return _patch(request, member.employer_id, mpk)

    @extend_schema(operation_id="employer_staff_withdraw", responses={204: None})
    def delete(self, request, mpk):
        member = _run(services.own_member, user=request.user)
        return _remove(request, member.employer_id, mpk)


# ---- staff side -----------------------------------------------------------------------------


def _employer(pk):
    if not employers.exists(pk):
        raise NotFound
    return pk


class StaffEmployerUsersView(APIView):
    """PI staff: an employer's portal users, and setting up its first account."""

    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "POST": INVITE}

    @extend_schema(operation_id="employers_users_list", responses={200: dict})
    def get(self, request, pk):
        _employer(pk)
        return Response(
            {
                "users": services.team(pk),
                "roles": [
                    {k: r[k] for k in ("id", "name", "description")}
                    for r in services.assignable_roles()
                ],
            }
        )

    @extend_schema(
        operation_id="employers_users_invite",
        request=EmployerInviteSerializer,
        responses={201: dict},
    )
    def post(self, request, pk):
        _employer(pk)
        s = EmployerInviteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        row = _run(
            services.invite,
            actor=request.user,
            employer_id=pk,
            first=not services.team(pk),
            **s.validated_data,
        )
        return Response(row, status=status.HTTP_201_CREATED)


class StaffEmployerUserView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"PATCH": INVITE, "DELETE": INVITE}

    @extend_schema(
        operation_id="employers_users_update", request=MemberPatchSerializer, responses={200: dict}
    )
    def patch(self, request, pk, mpk):
        return _patch(request, _employer(pk), mpk)

    @extend_schema(operation_id="employers_users_withdraw", responses={204: None})
    def delete(self, request, pk, mpk):
        return _remove(request, _employer(pk), mpk)
