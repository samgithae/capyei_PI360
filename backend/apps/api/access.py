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

    def scope_q(self, user, mapping: dict[str, str]) -> Q: ...


_backend: AccessBackend | None = None


def register(backend: AccessBackend) -> None:
    global _backend
    _backend = backend


def permissions_of(user) -> frozenset[str]:
    if _backend is None or not getattr(user, "is_authenticated", False):
        return frozenset()
    return _backend.permissions(user)


def has_permission(user, code: str) -> bool:
    return code in permissions_of(user)


def scope_q(user, mapping: dict[str, str]) -> Q:
    """Filter that keeps only rows inside the user's scope. ``mapping`` says which lookup
    holds each scope kind, e.g. ``{"cohort": "cohort_id", "officer": "assigned_officer_id"}``."""
    if _backend is None or not getattr(user, "is_authenticated", False):
        return DENY
    return _backend.scope_q(user, mapping)


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
