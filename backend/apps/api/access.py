"""Authorisation primitives every module can use (SEC-05, SEC-06, SEC-07, USR-09).

Domain modules may not import apps.identity, so they depend on this module instead. Identity
registers the real implementation at start-up (``register``). Until one is registered every
check denies: the API is closed by default.
"""

from __future__ import annotations

from typing import Protocol

from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models import Q
from rest_framework.permissions import BasePermission

DENY = Q(pk__in=[])


class AccessBackend(Protocol):
    def permissions(self, user) -> frozenset[str]: ...

    def roles(self, user) -> frozenset[str]: ...

    def scope_q(self, user, mapping: dict[str, str]) -> Q: ...

    def scope_values(self, user, kind: str) -> list | None: ...


_backend: AccessBackend | None = None


def register(backend: AccessBackend) -> None:
    global _backend
    _backend = backend


_mfa_policies: list = []


def register_mfa_policy(policy) -> None:
    """A portal module says when its own users need a second factor (a callable user -> bool)."""
    if policy not in _mfa_policies:
        _mfa_policies.append(policy)


def portal_mfa_required(user) -> bool:
    return any(policy(user) for policy in _mfa_policies)


def permissions_of(user) -> frozenset[str]:
    if _backend is None or not getattr(user, "is_authenticated", False):
        return frozenset()
    return _backend.permissions(user)


def roles_of(user) -> frozenset[str]:
    """Names of the user's active roles (used for feature-flag audiences)."""
    if _backend is None or not getattr(user, "is_authenticated", False):
        return frozenset()
    return _backend.roles(user)


def has_permission(user, code: str) -> bool:
    return code in permissions_of(user)


def scope_q(user, mapping: dict[str, str]) -> Q:
    """Filter that keeps only rows inside the user's scope. ``mapping`` says which lookup
    holds each scope kind, e.g. ``{"cohort": "cohort_id", "officer": "assigned_officer_id"}``."""
    if _backend is None or not getattr(user, "is_authenticated", False):
        return DENY
    return _backend.scope_q(user, mapping)


def scope_values(user, kind: str) -> list | None:
    """The values the user is assigned for one scope kind (e.g. project ids). ``None`` means the
    scope is not limited by that kind: an all-scope role. An empty list means the kind is not
    used for this user, so it does not narrow anything."""
    if _backend is None or not getattr(user, "is_authenticated", False):
        return []
    return _backend.scope_values(user, kind)


class HasPermission(BasePermission):
    """Deny by default. A view must declare ``required_permission``: a code, or a dict keyed
    by ``view.action`` or HTTP method. Anonymous callers get 401, signed-in ones 403."""

    def has_permission(self, request, view):
        required = getattr(view, "required_permission", None)
        if isinstance(required, dict):
            required = required.get(getattr(view, "action", None)) or required.get(request.method)
        if not required:
            return False
        return has_permission(request.user, required)


class ScopedQuerySet(models.QuerySet):
    """Querysets of scoped models. Set ``scope_map`` on the model class."""

    def visible_to(self, user):
        mapping = getattr(self.model, "scope_map", None)
        if not mapping:
            raise ImproperlyConfigured(f"{self.model.__name__} has no scope_map")
        return self.filter(scope_q(user, mapping))


class ScopedQuerysetMixin:
    """For DRF views: only rows in the caller's scope exist. Outside rows give 404, not 403,
    so a record's existence is not revealed."""

    def get_queryset(self):
        qs = super().get_queryset()
        if not isinstance(qs, ScopedQuerySet):
            raise ImproperlyConfigured("ScopedQuerysetMixin needs a ScopedQuerySet")
        return qs.visible_to(self.request.user)
