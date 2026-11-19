"""Public interface of apps.retention (T-073, DATA-12).

    retention.set_period(actor=u, data_class="import_rows", period_days=365, basis="...")
    retention.approve(actor=u, data_class="import_rows")
    retention.run(actor=None, apply=False)     # dry run: counts only
    retention.run(actor=None, apply=True)      # reduces every class that has a period + approval

A class is reduced only when it has a period and that exact period and basis were approved. A
dry run changes nothing. Every run, dry or applied, leaves a RetentionRun and an audit event
with counts only."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit

from .classes import REGISTRY
from .models import RetentionPolicy, RetentionRun


class RetentionError(Exception):
    def __init__(self, field, message, code="invalid"):
        super().__init__(message)
        self.field, self.message, self.code = field, message, code


def _class(code):
    try:
        return REGISTRY[code]
    except KeyError:
        raise RetentionError("data_class", "Unknown data class.", "not_found") from None


def _policy(code) -> RetentionPolicy:
    _class(code)
    return RetentionPolicy.objects.get_or_create(data_class=code)[0]


def state_of(policy: RetentionPolicy) -> str:
    if policy.period_days is None:
        return "not_set"
    return "active" if policy.approved_at else "awaiting_approval"


def _who(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or user.get_username()).strip()


def _row(code) -> dict:
    cls, p = REGISTRY[code], _policy(code)
    return {
        "code": cls.code,
        "label": cls.label,
        "description": cls.description,
        "removes": cls.removes,
        "keeps": cls.keeps,
        "minimum_days": cls.minimum_days,
        "period_days": p.period_days,
        "basis": p.basis,
        "state": state_of(p),
        "approved_by": _who(p.approved_by),
        "approved_at": p.approved_at.isoformat() if p.approved_at else None,
    }


def _run_row(r: RetentionRun) -> dict:
    return {
        "id": str(r.pk),
        "applied": r.applied,
        "by": r.actor_label or "system",
        "at": r.created_at.isoformat(),
        "results": r.results,
    }


def overview() -> dict:
    """Every class with its rule, and the latest runs."""
    return {
        "classes": [_row(c) for c in REGISTRY],
        "runs": [_run_row(r) for r in RetentionRun.objects.all()[:10]],
    }


def set_period(*, actor, data_class, period_days, basis) -> dict:
    """Set (or clear, with ``period_days=None``) the period. A change withdraws any approval."""
    cls = _class(data_class)
    basis = (basis or "").strip()
    if period_days is not None:
        if period_days < cls.minimum_days:
            raise RetentionError(
                "period_days", f"Keep at least {cls.minimum_days} days.", "too_short"
            )
        if not basis:
            raise RetentionError("basis", "Say why this period was chosen.", "required")
    with transaction.atomic():
        p = RetentionPolicy.objects.select_for_update().get_or_create(data_class=data_class)[0]
        if (p.period_days, p.basis) == (period_days, basis):
            return _row(data_class)
        before = {"period_days": p.period_days, "approved": bool(p.approved_at)}
        p.period_days, p.basis = period_days, basis if period_days is not None else ""
        p.approved_by, p.approved_at = None, None
        p.save()
        audit.record(
            actor=actor, action="retention.period_set", object_type="retention_policy",
            object_id=data_class, before=before,
            after={"period_days": period_days, "approved": False},
            reason=p.basis,
        )  # fmt: skip
    return _row(data_class)


def approve(*, actor, data_class) -> dict:
    with transaction.atomic():
        p = RetentionPolicy.objects.select_for_update().get_or_create(data_class=data_class)[0]
        _class(data_class)
        if p.period_days is None or not p.basis:
            raise RetentionError("period_days", "Set a period and its basis first.", "required")
        if p.approved_at:
            raise RetentionError("data_class", "This rule is already approved.", "conflict")
        p.approved_by, p.approved_at = actor, timezone.now()
        p.save()
        audit.record(
            actor=actor, action="retention.approved", object_type="retention_policy",
            object_id=data_class, after={"period_days": p.period_days},
        )  # fmt: skip
    return _row(data_class)


def revoke(*, actor, data_class, reason) -> dict:
    if not (reason or "").strip():
        raise RetentionError("reason", "Give a reason.", "required")
    with transaction.atomic():
        p = RetentionPolicy.objects.select_for_update().get_or_create(data_class=data_class)[0]
        _class(data_class)
        if not p.approved_at:
            raise RetentionError("data_class", "This rule is not approved.", "conflict")
        p.approved_by, p.approved_at = None, None
        p.save()
        audit.record(
            actor=actor, action="retention.revoked", object_type="retention_policy",
            object_id=data_class, reason=reason.strip(),
        )  # fmt: skip
    return _row(data_class)


def run(*, actor, apply=False, now=None) -> dict:
    """Count (dry run) or reduce (``apply``) every class. Classes without an approved period are
    reported as skipped and left alone; a dry run still counts what an approved rule would take."""
    now = now or timezone.now()
    results = {}
    for code, cls in REGISTRY.items():
        p = _policy(code)
        if p.period_days is None:
            results[code] = {"skipped": "no period set"}
            continue
        cutoff = now - timedelta(days=p.period_days)
        due = cls.count(cutoff)
        if not p.approved_at:
            results[code] = {"skipped": "not approved", "eligible": due}
        elif not apply:
            results[code] = {"eligible": due}
        else:
            with transaction.atomic():
                results[code] = {"eligible": due, "reduced": cls.reduce(cutoff)}
    with transaction.atomic():
        r = RetentionRun.objects.create(
            applied=apply, actor_label=(actor.get_username()[:150] if actor else "system"),
            results=results,
        )  # fmt: skip
        audit.record(
            actor=actor, action="retention.run" if apply else "retention.dry_run",
            object_type="retention_run", object_id=r.pk, after=results,
        )  # fmt: skip
    return _run_row(r)
