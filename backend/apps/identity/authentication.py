from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import SessionAuthentication


class SessionAuthentication401(SessionAuthentication):
    """Session cookie auth that answers 401 (not 403) when nobody is signed in, so the web
    client knows to show the sign-in page (doc 20 §4). 403 is kept for "signed in, not allowed"."""

    def authenticate_header(self, request):
        return "Session"


class SessionAuthentication401Scheme(OpenApiAuthenticationExtension):
    target_class = "apps.identity.authentication.SessionAuthentication401"
    name = "cookieAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": settings.SESSION_COOKIE_NAME}
