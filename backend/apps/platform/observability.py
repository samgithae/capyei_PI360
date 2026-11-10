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
from contextvars import ContextVar
from datetime import UTC, datetime

from django.core.signals import request_finished
from django.dispatch import receiver

HEADER = "X-Request-ID"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_current: ContextVar[str | None] = ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    return _current.get()


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(HEADER, "")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        request.request_id = request_id
        # Cleared on request_finished, not here, so Django's own response log
        # line ("Bad Request: ...") still carries the ID.
        _current.set(request_id)
        response = self.get_response(request)
        response[HEADER] = request_id
        return response


@receiver(request_finished)
def _clear_request_id(**kwargs):
    _current.set(None)


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = _current.get()
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
