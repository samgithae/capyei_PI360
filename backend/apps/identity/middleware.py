"""Absolute session lifetime (SEC-11). The idle timeout is Django's SESSION_COOKIE_AGE with
SESSION_SAVE_EVERY_REQUEST, so each request pushes expiry out by the idle period."""

import time

from django.conf import settings
from django.contrib.auth import logout

STARTED = "auth_started_at"


class SessionPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            started = request.session.get(STARTED)
            if started is None:
                request.session[STARTED] = time.time()  # session predates the policy
            elif time.time() - started > settings.SESSION_ABSOLUTE_SECONDS:
                logout(request)  # request.user becomes anonymous for this request
        return self.get_response(request)
