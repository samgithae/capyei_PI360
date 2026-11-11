"""Public interface of apps.intelligence (CMP-09). Other modules import only this module.

T-047: rule sets and the lifecycle of their versions (doc 07 §2.4)

    draft -> in review -> approved -> active -> retired

A definition can be edited only in draft. Activation retires the version it replaces, and an
emergency deactivation falls back to that version. Every step writes an audit event in the same
transaction as the change."""

import hashlib
import json
from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone

import pi360_rules
from apps.audit import services as audit

from .models import RuleSet, RuleVersion

EMPTY = {"factors": [], "parameters": {}}


class RuleViolation(Exception):
    def __init__(self, field, message, code):
        super().__init__(message)
        self.field, self.message, self.code = field, message, code


def definition_hash(definition) -> str:
    """Fingerprint of a definition. Key order does not change it."""
    text = json.dumps(definition, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def problems(version) -> list[dict]:
    return pi360_rules.validate(version.definition)


def unapproved(version) -> list[str]:
    return pi360_rules.unapproved(version.definition)


def _state(version) -> dict:
    """What an audit event records about a version: never the whole definition, only its
    fingerprint and size."""
    d = version.definition if isinstance(version.definition, dict) else {}
    return {
        "status": version.status,
        "definition_hash": definition_hash(version.definition),
        "factors": len(d.get("factors") or []),
        "parameters": len(d.get("parameters") or {}),
    }


def _changes(old, new) -> dict:
    """Which factors and parameters differ between two definitions, for the audit trail."""
    old = old if isinstance(old, dict) else {}
    new = new if isinstance(new, dict) else {}

    def factors(d):
        fs = d.get("factors")
        return {
            f["code"]: f for f in (fs if isinstance(fs, list) else [])
            if isinstance(f, dict) and isinstance(f.get("code"), str)
        }  # fmt: skip

    def params(d):
        ps = d.get("parameters")
        return ps if isinstance(ps, dict) else {}

    fo, fn, po, pn = factors(old), factors(new), params(old), params(new)
    out = {
        "factors_added": sorted(set(fn) - set(fo)),
        "factors_removed": sorted(set(fo) - set(fn)),
        "factors_changed": sorted(c for c in set(fo) & set(fn) if fo[c] != fn[c]),
        "parameters_added": sorted(set(pn) - set(po)),
        "parameters_removed": sorted(set(po) - set(pn)),
        "parameters_changed": {
            name: {"from": _brief(po[name]), "to": _brief(pn[name])}
            for name in sorted(set(po) & set(pn))
            if po[name] != pn[name]
        },
    }
    return {k: v for k, v in out.items() if v}


def _brief(p):
    return {"value": p.get("value"), "approved": p.get("approved", False)} if (
        isinstance(p, dict)
    ) else p  # fmt: skip


def _record(actor, action, version, before=None, reason="", extra=None):
    audit.record(
        actor=actor,
        action=action,
        object_type="rule_version",
        object_id=version.pk,
        before=before,
        after={**_state(version), **(extra or {})},
        reason=reason,
    )


def _locked(version) -> RuleVersion:
    """Re-read the version inside the transaction, holding its row until commit."""
    return (
        RuleVersion.objects.select_for_update(of=("self",))
        .select_related("rule_set")
        .get(pk=version.pk)
    )


def _need(version, *statuses, doing):
    if version.status not in statuses:
        names = dict(RuleVersion.STATUSES)
        allowed = " or ".join(names[s].lower() for s in statuses)
        raise RuleViolation(
            "status",
            f"Only a version that is {allowed} can be {doing}. "
            f"This one is {names[version.status].lower()}.",
            "wrong_status",
        )


# ---- rule sets -------------------------------------------------------------------------------


@transaction.atomic
def create_rule_set(*, actor, module, code, name, purpose="", definition=None, change_notes=""):
    """A new rule set with version 1 as a draft."""
    if module not in pi360_rules.MODULES:
        raise RuleViolation("module", "Choose module A, B or C.", "unknown_module")
    if RuleSet.objects.filter(code=code).exists():
        raise RuleViolation("code", "A rule set with this code already exists.", "duplicate_code")
    rule_set = RuleSet.objects.create(
        module=module, code=code, name=name.strip(), purpose=purpose.strip(), created_by=actor
    )
    audit.record(
        actor=actor,
        action="rule_set.created",
        object_type="rule_set",
        object_id=rule_set.pk,
        after={"module": module, "code": code, "name": rule_set.name},
    )
    version = RuleVersion.objects.create(
        rule_set=rule_set,
        number=1,
        definition=definition if definition is not None else dict(EMPTY),
        change_notes=change_notes,
        created_by=actor,
    )
    _record(actor, "rule_version.created", version)
    return rule_set


def active_version(code: str) -> RuleVersion | None:
    """The version in force for a rule set, or None when nothing has been activated yet."""
    return (
        RuleVersion.objects.select_related("rule_set")
        .filter(rule_set__code=code, status=RuleVersion.ACTIVE)
        .first()
    )


# ---- drafting --------------------------------------------------------------------------------


@transaction.atomic
def clone(*, actor, version, change_notes="") -> RuleVersion:
    """A new draft that starts as a copy of ``version`` (normally the active one)."""
    source = _locked(version)
    last = (
        RuleVersion.objects.filter(rule_set=source.rule_set).order_by("-number")
        .values_list("number", flat=True).first()
    )  # fmt: skip
    try:
        with transaction.atomic():
            draft = RuleVersion.objects.create(
                rule_set=source.rule_set,
                number=(last or 0) + 1,
                definition=json.loads(json.dumps(source.definition)),  # a deep copy
                change_notes=change_notes,
                cloned_from=source,
                created_by=actor,
            )
    except IntegrityError:
        raise RuleViolation(
            "version", "Another draft was created at the same moment. Try again.", "number_taken"
        ) from None
    _record(actor, "rule_version.created", draft, extra={"cloned_from": source.number})
    return draft


@transaction.atomic
def update_draft(*, actor, version, definition=None, change_notes=None) -> RuleVersion:
    v = _locked(version)
    _need(v, RuleVersion.DRAFT, doing="edited")
    before, old = _state(v), v.definition
    if definition is not None:
        if not isinstance(definition, dict):
            raise RuleViolation("definition", "The definition must be a JSON object.", "invalid")
        v.definition = definition
    if change_notes is not None:
        v.change_notes = change_notes
    v.save()
    changes = _changes(old, v.definition)
    if changes or change_notes is not None:
        _record(actor, "rule_version.edited", v, before, extra={"changes": changes})
    return v


@transaction.atomic
def discard(*, actor, version) -> None:
    v = _locked(version)
    _need(v, RuleVersion.DRAFT, doing="discarded")
    before = _state(v)
    audit.record(
        actor=actor,
        action="rule_version.discarded",
        object_type="rule_version",
        object_id=v.pk,
        before=before,
        after={"rule_set": v.rule_set.code, "number": v.number},
    )
    v.delete()


# ---- review ----------------------------------------------------------------------------------


@transaction.atomic
def submit(*, actor, version) -> RuleVersion:
    """Send a draft for review. The definition must be well formed."""
    v = _locked(version)
    _need(v, RuleVersion.DRAFT, doing="sent for review")
    found = problems(v)
    if found:
        first = found[0]
        more = f" ({len(found) - 1} more)" if len(found) > 1 else ""
        raise RuleViolation(
            "definition",
            f"Fix the definition first: {first['path']}: {first['message']}{more}",
            "invalid_definition",
        )
    before = _state(v)
    v.status, v.submitted_by, v.submitted_at = RuleVersion.IN_REVIEW, actor, timezone.now()
    v.save()
    _record(actor, "rule_version.submitted", v, before)
    return v


@transaction.atomic
def send_back(*, actor, version, note) -> RuleVersion:
    """Return a version to draft so it can be edited again. Not possible once it has been
    active."""
    v = _locked(version)
    _need(v, RuleVersion.IN_REVIEW, RuleVersion.APPROVED, doing="returned to draft")
    if not note.strip():
        raise RuleViolation("note", "Say what needs to change.", "note_required")
    before = _state(v)
    v.status = RuleVersion.DRAFT
    v.approved_by = v.approved_at = None
    v.save()
    _record(actor, "rule_version.returned", v, before, reason=note.strip())
    return v


@transaction.atomic
def approve(*, actor, version, note="") -> RuleVersion:
    """Approve a version in review. Every parameter must have an approved value first, so a
    threshold nobody has decided can never reach production."""
    v = _locked(version)
    _need(v, RuleVersion.IN_REVIEW, doing="approved")
    waiting = unapproved(v)
    if waiting:
        raise RuleViolation(
            "parameters",
            "These parameters still wait for a decision: " + ", ".join(waiting) + ".",
            "unapproved_parameters",
        )
    before = _state(v)
    v.status, v.approved_by, v.approved_at = RuleVersion.APPROVED, actor, timezone.now()
    v.save()
    _record(actor, "rule_version.approved", v, before, reason=note.strip())
    return v


# ---- activation ------------------------------------------------------------------------------


@transaction.atomic
def activate(*, actor, version, note="") -> RuleVersion:
    """Put an approved version into force. The version it replaces is retired."""
    v = _locked(version)
    _need(v, RuleVersion.APPROVED, doing="activated")
    now = timezone.now()
    current = (
        RuleVersion.objects.select_for_update()
        .filter(rule_set=v.rule_set, status=RuleVersion.ACTIVE)
        .first()
    )
    if current is not None:
        was = _state(current)
        current.status, current.retired_at = RuleVersion.RETIRED, now
        current.save()
        _record(actor, "rule_version.retired", current, was, extra={"replaced_by": v.number})
    before = _state(v)
    v.status, v.activated_by, v.effective_from, v.replaced = RuleVersion.ACTIVE, actor, now, current
    v.save()
    _record(
        actor, "rule_version.activated", v, before, reason=note.strip(),
        extra={
            "rule_set": v.rule_set.code,
            "number": v.number,
            "replaced": current.number if current else None,
        },
    )  # fmt: skip
    return v


@transaction.atomic
def deactivate(*, actor, version, reason) -> RuleVersion | None:
    """Emergency stop (doc 07 §2.4). Retires the active version and brings back the version it
    replaced. Returns the version now in force, or None when there was nothing to fall back
    to (the module then produces no output for this rule set)."""
    v = _locked(version)
    _need(v, RuleVersion.ACTIVE, doing="deactivated")
    if not reason.strip():
        raise RuleViolation("note", "Say why this version is being deactivated.", "reason_required")
    now = timezone.now()
    before = _state(v)
    v.status, v.retired_at = RuleVersion.RETIRED, now
    v.save()
    fallback = None
    if v.replaced_id:
        fallback = RuleVersion.objects.select_for_update().filter(
            pk=v.replaced_id, status=RuleVersion.RETIRED
        ).first()  # fmt: skip
    _record(
        actor, "rule_version.deactivated", v, before, reason=reason.strip(),
        extra={"fallback": fallback.number if fallback else None},
    )  # fmt: skip
    if fallback is not None:
        was = _state(fallback)
        fallback.status, fallback.retired_at = RuleVersion.ACTIVE, None
        fallback.save()
        _record(
            actor, "rule_version.reactivated", fallback, was, reason=reason.strip(),
            extra={"after_deactivating": v.number},
        )  # fmt: skip
    return fallback


# ---- evaluation ------------------------------------------------------------------------------


def mark_used(version) -> None:
    """Remember that a stored result relies on this version (ADR-003: immutable once used)."""
    if version.used_at is None:
        RuleVersion.objects.filter(pk=version.pk, used_at__isnull=True).update(
            used_at=timezone.now()
        )


def evaluate(code: str, snapshot: dict, today: date) -> dict | None:
    """Evaluate the active version of a rule set against a snapshot. None when the rule set
    has no active version. The caller stores the result with ``version_id`` and the snapshot."""
    version = active_version(code)
    if version is None:
        return None
    result = pi360_rules.evaluate(
        version.definition, snapshot, today, module=version.rule_set.module
    )
    return {"version_id": str(version.pk), "version": version.number, **result}
