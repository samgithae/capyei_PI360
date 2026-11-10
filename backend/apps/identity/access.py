"""Identity's implementation of apps.api.access (registered in AppConfig.ready)."""

from django.db.models import Q
from django.utils import timezone

from apps.api.access import DENY

from .catalogue import ROLE_ASSIGNABLE
from .models import PermissionGrant, Role, ScopeAssignment

CACHE = "_pi_access"


def _roles(user):
    return Role.objects.filter(active=True, assignments__user=user).distinct()


def _compute(user) -> dict:
    perms: set[str] = set()
    all_scope = False
    if user.is_active and user.is_superuser:
        perms |= ROLE_ASSIGNABLE  # never the grant-only groups
        all_scope = True
    if user.is_active:
        for role in _roles(user):
            perms |= set(role.permissions) & ROLE_ASSIGNABLE
            all_scope = all_scope or role.scope_mode == Role.SCOPE_ALL
        now = timezone.now()
        perms |= set(
            PermissionGrant.objects.filter(
                user=user, revoked_at__isnull=True, expires_at__gt=now
            ).values_list("permission", flat=True)
        )
    return {"perms": frozenset(perms), "all_scope": all_scope}


def _state(user) -> dict:
    state = getattr(user, CACHE, None)
    if state is None:
        state = _compute(user)
        setattr(user, CACHE, state)  # per request: users are rebuilt on every request
    return state


def scope_summary(user) -> dict:
    state = _state(user)
    rows = ScopeAssignment.objects.filter(user=user).order_by("kind", "value")
    return {
        "mode": "all" if state["all_scope"] else "assigned",
        "assignments": [{"kind": r.kind, "value": r.value} for r in rows],
    }


class IdentityAccess:
    def roles(self, user) -> frozenset[str]:
        if not user.is_active:
            return frozenset()
        return frozenset(_roles(user).values_list("name", flat=True))

    def permissions(self, user) -> frozenset[str]:
        return _state(user)["perms"]

    def scope_q(self, user, mapping: dict[str, str]) -> Q:
        state = _state(user)
        if not user.is_active:
            return DENY
        if state["all_scope"]:
            return Q()
        by_kind: dict[str, list] = {}
        for row in ScopeAssignment.objects.filter(user=user):
            if row.kind in mapping:
                value = user.pk if (row.kind == "officer" and row.value == "self") else row.value
                by_kind.setdefault(row.kind, []).append(value)
        if not by_kind:
            return DENY  # nothing assigned, or nothing this model can be scoped by
        q = Q()
        for kind, values in by_kind.items():
            q &= Q(**{f"{mapping[kind]}__in": values})
        return q
