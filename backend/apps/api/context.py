"""Per-request context shared by logging (CMP-15) and audit (CMP-13).

Set by the request-ID middleware, cleared when the request finishes. Jobs and
shell sessions have no request, so every reader must accept ``None``.
"""

from contextvars import ContextVar

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)
