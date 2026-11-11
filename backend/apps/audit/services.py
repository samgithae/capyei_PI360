"""Public interface of apps.audit (CMP-13). Every other module records through `record`.

    from apps.audit import services as audit
    audit.record(actor=request.user, action="referral.stage_changed",
                 object_type="referral", object_id=ref.pk,
                 before={"stage": "offered"}, after={"stage": "placed"}, reason="...")

Call it inside the same transaction as the change it describes, so both commit or neither does.
"""

from dataclasses import dataclass

from django.db import connection, transaction
from django.utils import timezone

from apps.api import context

from .chain import GENESIS, compute_hash, event_fields
from .models import AuditEvent

# Serialises writers so each event sees the previous event's hash. Any fixed number.
_LOCK_KEY = 7_203_700_013


def _actor(actor):
    if actor is None:
        return None, "system"
    return getattr(actor, "pk", None), actor.get_username()[:150]


def record(
    *, actor, action, object_type, object_id, before=None, after=None, reason="", at=None
) -> AuditEvent:
    """Append one event. ``actor`` is a user, or None for the system (jobs, migrations)."""
    actor_id, label = _actor(actor)
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_LOCK_KEY])
        last = AuditEvent.objects.order_by("-pk").values_list("hash", flat=True).first()
        prev_hash = last or GENESIS
        event = AuditEvent(
            at=at or timezone.now(),
            actor_id=actor_id,
            actor_label=label,
            action=action,
            object_type=object_type,
            object_id=str(object_id),
            before=before,
            after=after,
            reason=reason,
            request_id=context.request_id.get() or "",
            ip=context.client_ip.get(),
            prev_hash=prev_hash,
        )
        event.hash = compute_hash(prev_hash, event_fields(event))
        event.save()
    return event


@dataclass(frozen=True)
class ChainResult:
    ok: bool
    checked: int
    first_bad_id: int | None = None
    problem: str = ""


def verify_chain(*, batch_size: int = 2000) -> ChainResult:
    """Recompute every hash from the start. Reports the first row that does not match."""
    expected_prev = GENESIS
    checked = 0
    last_id = 0
    while True:
        rows = list(AuditEvent.objects.filter(pk__gt=last_id).order_by("pk")[:batch_size])
        if not rows:
            return ChainResult(True, checked)
        for ev in rows:
            if ev.prev_hash != expected_prev:
                return ChainResult(False, checked, ev.pk, "link to previous event is broken")
            if ev.hash != compute_hash(ev.prev_hash, event_fields(ev)):
                return ChainResult(False, checked, ev.pk, "event content does not match its hash")
            expected_prev = ev.hash
            checked += 1
            last_id = ev.pk


def history(object_type: str, object_id, limit: int = 200) -> list[dict]:
    """Newest-first change history of one object, for record history panels."""
    events = AuditEvent.objects.filter(object_type=object_type, object_id=str(object_id))
    return [
        {
            "at": e.at.isoformat(),
            "actor": e.actor_label,
            "action": e.action,
            "before": e.before,
            "after": e.after,
            "reason": e.reason,
        }
        for e in events.order_by("-at", "-pk")[:limit]
    ]


def set_archived(*, actor, queryset, ids, archive: bool, object_type: str, reason: str = ""):
    """Archive or restore the records in ``queryset`` whose pk is in ``ids``."""
    found = {str(o.pk): o for o in queryset.filter(pk__in=ids)}
    changed, skipped = [], []
    with transaction.atomic():
        for pk in dict.fromkeys(str(i) for i in ids):
            obj = found.get(pk)
            if obj is None:
                skipped.append({"id": pk, "reason": "Not found."})
            elif (obj.archived_at is not None) == archive:
                skipped.append(
                    {"id": pk, "reason": "Already archived." if archive else "Not archived."}
                )
            else:
                obj.archived_at = timezone.now() if archive else None
                obj.save(update_fields=["archived_at"])
                record(
                    actor=actor,
                    action=f"{object_type}.{'archived' if archive else 'restored'}",
                    object_type=object_type,
                    object_id=obj.pk,
                    before={"archived": not archive},
                    after={"archived": archive},
                    reason=reason,
                )
                changed.append(pk)
    return {"changed": changed, "skipped": skipped}
