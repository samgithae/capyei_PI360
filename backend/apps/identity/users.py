"""Staff account administration (FR-03, USR-02, SEC-08). Every change is audited in the same
transaction. Roles, scopes and grants live in ``services``; this module owns the account itself."""

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import transaction
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.audit import services as audit

from . import services
from .models import Role, RoleAssignment

User = get_user_model()


def _snapshot(user):
    return {
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
    }


def revoke_sessions(user) -> int:
    """End every signed-in session of the user. Returns how many were removed."""
    uid, doomed = str(user.pk), []
    for s in Session.objects.iterator():
        if s.get_decoded().get("_auth_user_id") == uid:
            doomed.append(s.pk)
    Session.objects.filter(pk__in=doomed).delete()
    return len(doomed)


def _last_administrator(user) -> bool:
    """True if ``user`` is the only active account holding the active Administrator role."""
    holders = RoleAssignment.objects.filter(
        role__name=services.ADMIN_ROLE, role__active=True, user__is_active=True
    ).values_list("user_id", flat=True)
    return set(holders) == {user.pk}


@transaction.atomic
def create_user(*, actor, username, email, first_name="", last_name="", roles=()):
    username, email = username.strip(), email.strip().lower()
    if User.objects.filter(username__iexact=username).exists():
        raise services.AccessError("username", "This username is already in use.")
    if User.objects.filter(email__iexact=email).exists():
        raise services.AccessError("email", "This email address is already in use.")
    user = User(username=username, email=email, first_name=first_name, last_name=last_name)
    user.set_unusable_password()  # the person sets a password through the reset link
    user.save()
    audit.record(
        actor=actor,
        action="user.created",
        object_type="user",
        object_id=user.pk,
        after=_snapshot(user),
    )
    for role in Role.objects.filter(pk__in=roles):
        services.assign_role(actor=actor, user=user, role=role)
    return user


@transaction.atomic
def update_user(*, actor, user, **changes):
    before = _snapshot(user)
    if "email" in changes:
        email = changes["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            raise services.AccessError("email", "This email address is already in use.")
        changes["email"] = email
    for field in ("email", "first_name", "last_name"):
        if field in changes:
            setattr(user, field, changes[field])
    if _snapshot(user) != before:
        user.save()
        audit.record(
            actor=actor,
            action="user.changed",
            object_type="user",
            object_id=user.pk,
            before=before,
            after=_snapshot(user),
        )
    return user


@transaction.atomic
def suspend_user(*, actor, user, reason):
    if not reason.strip():
        raise services.AccessError("reason", "State why the account is suspended.")
    if actor is not None and actor.pk == user.pk:
        raise services.AccessError("user", "You cannot suspend your own account.")
    if user.is_active and _last_administrator(user):
        raise services.AccessError("user", "This is the last active Administrator.")
    if not user.is_active:
        return user
    user.is_active = False
    user.save(update_fields=["is_active"])
    ended = revoke_sessions(user)
    audit.record(
        actor=actor,
        action="user.suspended",
        object_type="user",
        object_id=user.pk,
        before={"is_active": True},
        after={"is_active": False, "sessions_ended": ended},
        reason=reason.strip(),
    )
    return user


@transaction.atomic
def reactivate_user(*, actor, user, reason=""):
    if user.is_active:
        return user
    user.is_active = True
    user.save(update_fields=["is_active"])
    audit.record(
        actor=actor,
        action="user.reactivated",
        object_type="user",
        object_id=user.pk,
        before={"is_active": False},
        after={"is_active": True},
        reason=reason.strip(),
    )
    return user


@transaction.atomic
def reset_mfa(*, actor, user, reason):
    """Remove the user's authenticator so they enrol a new one at next sign-in."""
    if not reason.strip():
        raise services.AccessError("reason", "State why the second factor is being reset.")
    removed, _ = TOTPDevice.objects.filter(user=user).delete()
    ended = revoke_sessions(user)
    audit.record(
        actor=actor,
        action="user.mfa_reset",
        object_type="user",
        object_id=user.pk,
        after={"devices_removed": removed, "sessions_ended": ended},
        reason=reason.strip(),
    )


@transaction.atomic
def set_roles(*, actor, user, role_ids):
    """Make the user's roles exactly ``role_ids``."""
    wanted = set(Role.objects.filter(pk__in=role_ids).values_list("pk", flat=True))
    missing = set(role_ids) - wanted
    if missing:
        raise services.AccessError("roles", f"Unknown role id: {sorted(missing)[0]}")
    current = {a.role_id: a.role for a in user.role_assignments.select_related("role")}
    admin_pk = Role.objects.filter(name=services.ADMIN_ROLE).values_list("pk", flat=True).first()
    if admin_pk in current and admin_pk not in wanted:
        if user.is_active and _last_administrator(user):
            raise services.AccessError("roles", "This is the last active Administrator.")
    for pk, role in current.items():
        if pk not in wanted:
            services.remove_role(actor=actor, user=user, role=role)
    for role in Role.objects.filter(pk__in=wanted - set(current)):
        services.assign_role(actor=actor, user=user, role=role)
