"""Identity's public interface: roles, assignments, scopes and grants (FR-04, USR-09, SEC-18).
Every change is audited in the same transaction."""

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit

from .catalogue import BY_CODE, GRANT_ONLY, ROLE_ASSIGNABLE
from .defaults import DEFAULT_ROLES
from .models import PermissionGrant, Role, RoleAssignment, ScopeAssignment

ADMIN_ROLE = "Administrator"
MUST_KEEP = "identity.manage_roles"  # the Administrator role cannot lose this


class AccessError(ValueError):
    """A rule of the access model was broken. ``field`` names the input at fault."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field, self.message = field, message


def ensure_default_roles() -> None:
    """Create any shipped role that is missing. Never overwrites what administrators changed."""
    for spec in DEFAULT_ROLES:
        Role.objects.get_or_create(name=spec["name"], defaults={**spec, "is_system": True})


def _check_permissions(codes):
    codes = list(dict.fromkeys(codes))
    unknown = [c for c in codes if c not in BY_CODE]
    if unknown:
        raise AccessError("permissions", f"Unknown permission: {unknown[0]}")
    restricted = [c for c in codes if c in GRANT_ONLY]
    if restricted:
        raise AccessError(
            "permissions", f"{restricted[0]} is given to a named user as a grant, not in a role."
        )
    return sorted(codes)


def _snapshot(role):
    return {
        "name": role.name,
        "permissions": role.permissions,
        "scope_mode": role.scope_mode,
        "active": role.active,
    }


@transaction.atomic
def create_role(*, actor, name, description="", permissions=(), scope_mode="assigned", active=True):
    name = name.strip()
    if Role.objects.filter(name__iexact=name).exists():
        raise AccessError("name", "A role with this name already exists.")
    role = Role.objects.create(
        name=name,
        description=description,
        permissions=_check_permissions(permissions),
        scope_mode=scope_mode,
        active=active,
    )
    audit.record(
        actor=actor,
        action="role.created",
        object_type="role",
        object_id=role.pk,
        after=_snapshot(role),
    )
    return role


@transaction.atomic
def update_role(*, actor, role, **changes):
    before = _snapshot(role)
    if "name" in changes:
        name = changes["name"].strip()
        if role.is_system and name != role.name:
            raise AccessError("name", "Shipped roles keep their name.")
        if Role.objects.filter(name__iexact=name).exclude(pk=role.pk).exists():
            raise AccessError("name", "A role with this name already exists.")
        role.name = name
    if "description" in changes:
        role.description = changes["description"]
    if "permissions" in changes:
        role.permissions = _check_permissions(changes["permissions"])
    if "scope_mode" in changes:
        role.scope_mode = changes["scope_mode"]
    if "active" in changes:
        role.active = changes["active"]
    if role.name == ADMIN_ROLE and (MUST_KEEP not in role.permissions or not role.active):
        raise AccessError("permissions", "Administrators must keep the ability to manage roles.")
    role.save()
    after = _snapshot(role)
    if after != before:
        audit.record(
            actor=actor,
            action="role.changed",
            object_type="role",
            object_id=role.pk,
            before=before,
            after=after,
        )
    return role


@transaction.atomic
def delete_role(*, actor, role):
    if role.is_system:
        raise AccessError("role", "Shipped roles cannot be deleted. Switch them off instead.")
    if role.assignments.exists():
        raise AccessError("role", "Remove the role from its users first.")
    before = _snapshot(role)
    pk = role.pk
    role.delete()
    audit.record(
        actor=actor, action="role.deleted", object_type="role", object_id=pk, before=before
    )


@transaction.atomic
def assign_role(*, actor, user, role):
    _, created = RoleAssignment.objects.get_or_create(user=user, role=role)
    if created:
        audit.record(
            actor=actor,
            action="user.role_assigned",
            object_type="user",
            object_id=user.pk,
            after={"role": role.name},
        )


@transaction.atomic
def remove_role(*, actor, user, role):
    deleted, _ = RoleAssignment.objects.filter(user=user, role=role).delete()
    if deleted:
        audit.record(
            actor=actor,
            action="user.role_removed",
            object_type="user",
            object_id=user.pk,
            before={"role": role.name},
        )


@transaction.atomic
def set_scopes(*, actor, user, scopes):
    """Replace the user's scope assignments. ``scopes`` is a list of (kind, value)."""
    valid = {k for k, _ in ScopeAssignment.KINDS}
    wanted = set()
    for kind, value in scopes:
        if kind not in valid:
            raise AccessError("scopes", f"Unknown scope kind: {kind}")
        if not str(value).strip():
            raise AccessError("scopes", "A scope needs a value.")
        wanted.add((kind, str(value).strip()))
    current = set(ScopeAssignment.objects.filter(user=user).values_list("kind", "value"))
    if wanted == current:
        return
    ScopeAssignment.objects.filter(user=user).delete()
    ScopeAssignment.objects.bulk_create(
        [ScopeAssignment(user=user, kind=k, value=v) for k, v in sorted(wanted)]
    )
    audit.record(
        actor=actor,
        action="scope.assigned",
        object_type="user",
        object_id=user.pk,
        before={"scopes": sorted(current)},
        after={"scopes": sorted(wanted)},
    )


@transaction.atomic
def grant_permission(*, actor, user, permission, purpose, expires_at: datetime):
    if permission not in GRANT_ONLY:
        raise AccessError("permission", "Only restricted permissions are given as grants.")
    if not purpose.strip():
        raise AccessError("purpose", "State the purpose of the grant.")
    if expires_at <= timezone.now():
        raise AccessError("expires_at", "The expiry must be in the future.")
    grant = PermissionGrant.objects.create(
        user=user,
        permission=permission,
        purpose=purpose.strip(),
        granted_by=actor,
        expires_at=expires_at,
    )
    audit.record(
        actor=actor,
        action="permission.granted",
        object_type="user",
        object_id=user.pk,
        after={"permission": permission, "expires_at": expires_at.isoformat()},
        reason=purpose.strip(),
    )
    return grant


@transaction.atomic
def revoke_grant(*, actor, grant, reason=""):
    if grant.revoked_at:
        return
    grant.revoked_at = timezone.now()
    grant.save(update_fields=["revoked_at"])
    audit.record(
        actor=actor,
        action="permission.revoked",
        object_type="user",
        object_id=grant.user_id,
        before={"permission": grant.permission},
        reason=reason,
    )


def _user_model():
    from django.contrib.auth import get_user_model

    return get_user_model()


@transaction.atomic
def create_pending_account(*, actor, email, role_name):
    """An inactive account with no usable password, to be activated by its owner through a
    one-time link. The e-mail is the user name. An existing user is never reused."""
    User = _user_model()
    email = email.strip().lower()
    if (
        User.objects.filter(username__iexact=email).exists()
        or User.objects.filter(email__iexact=email).exists()
    ):
        raise AccessError("email", "An account already uses this e-mail address.")
    role = Role.objects.filter(name=role_name, active=True).first()
    if role is None:
        raise AccessError("role", f"The {role_name} role is not available.")
    user = User(username=email, email=email, is_active=False)
    user.set_unusable_password()
    user.save()
    assign_role(actor=actor, user=user, role=role)
    audit.record(
        actor=actor,
        action="user.pending_account_created",
        object_type="user",
        object_id=user.pk,
        after={"role": role_name},
    )
    return user


def activate_account(*, user, password):
    """Set the owner's first password and switch the account on."""
    from django.contrib.auth import password_validation as pv
    from django.core.exceptions import ValidationError

    try:
        pv.validate_password(password, user)
    except ValidationError as exc:
        raise AccessError("password", " ".join(exc.messages)) from exc
    user.set_password(password)
    user.is_active = True
    user.save(update_fields=["password", "is_active"])
    audit.record(actor=user, action="user.account_activated", object_type="user", object_id=user.pk)


def delete_pending_account(*, actor, user):
    """Remove an account that was never activated (an invite withdrawn or replaced)."""
    if user.is_active or user.has_usable_password():
        raise AccessError("user", "Only an account that was never activated can be removed.")
    pk = user.pk
    user.delete()
    audit.record(
        actor=actor, action="user.pending_account_removed", object_type="user", object_id=pk
    )


def role_names(user) -> list[str]:
    return sorted(
        Role.objects.filter(active=True, assignments__user=user).values_list("name", flat=True)
    )


__all__ = [
    "AccessError",
    "ROLE_ASSIGNABLE",
    "activate_account",
    "assign_role",
    "create_pending_account",
    "create_role",
    "delete_pending_account",
    "delete_role",
    "ensure_default_roles",
    "grant_permission",
    "remove_role",
    "revoke_grant",
    "role_names",
    "set_scopes",
    "update_role",
]
