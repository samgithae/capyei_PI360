"""Request IDs and structured JSON logs (doc 04 CMP-15).

Every request gets an ID: the caller's X-Request-ID if it is safe, otherwise a
new UUID. The ID is echoed in the response header, added to every log line
written while the request runs, and put on ``request.request_id`` so problem
responses and audit events can carry it.
"""

import json
import logging
import re
import uuid
from datetime import UTC, datetime

from django.conf import settings
from django.core.signals import request_finished
from django.dispatch import receiver

from apps.api import context

HEADER = "X-Request-ID"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def current_request_id() -> str | None:
    return context.request_id.get()


def _client_ip(request):
    """Behind our nginx the socket peer is the proxy, so the real address is the last
    X-Forwarded-For hop (the one nginx appended). Only trusted when TRUST_X_FORWARDED_FOR is
    on, because a client can send the header itself when there is no proxy."""
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        hops = [h.strip() for h in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")]
        if hops and hops[-1]:
            return hops[-1]
    return request.META.get("REMOTE_ADDR")


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(HEADER, "")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        request.request_id = request_id
        # Cleared on request_finished, not here, so Django's own response log
        # line ("Bad Request: ...") still carries the ID.
        context.request_id.set(request_id)
        context.client_ip.set(_client_ip(request))
        response = self.get_response(request)
        response[HEADER] = request_id
        return response


@receiver(request_finished)
def _clear_request_id(**kwargs):
    context.request_id.set(None)
    context.client_ip.set(None)


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = context.request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Never log personal data: callers pass IDs, not values."""

    def format(self, record):
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)
