"""Gate a view behind a feature flag: with the flag off the route does not exist (404)."""

from django.http import Http404
from rest_framework.permissions import BasePermission

from .services import is_enabled


class FlagGate(BasePermission):
    """Put after HasPermission. Set ``required_flag = "key"`` on the view."""

    def has_permission(self, request, view):
        key = getattr(view, "required_flag", None)
        if key and not is_enabled(key, request.user):
            raise Http404
        return True
