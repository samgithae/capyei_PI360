"""Hash chain for tamper evidence (SEC-09, doc 05).

hash = SHA-256(prev_hash + canonical JSON of the event's fields). Changing, removing or
reordering any row breaks every later hash, so verification finds the first bad row.
The chain is continuous across days, which is stronger than the per-day chain in doc 04.
"""

import hashlib
import json
from datetime import UTC

GENESIS = "0" * 64


def canonical(fields: dict) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(prev_hash: str, fields: dict) -> str:
    return hashlib.sha256((prev_hash + canonical(fields)).encode("utf-8")).hexdigest()


def event_fields(event) -> dict:
    """The fields covered by the hash, in a form that survives a database round trip."""
    return {
        "at": event.at.astimezone(UTC).isoformat(timespec="microseconds"),
        "actor_id": event.actor_id,
        "actor_label": event.actor_label,
        "action": event.action,
        "object_type": event.object_type,
        "object_id": event.object_id,
        "before": event.before,
        "after": event.after,
        "reason": event.reason,
        "request_id": event.request_id,
        "ip": event.ip,
    }
