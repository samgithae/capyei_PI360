"""Corrections to MIS data (T-074, D-025 option a).

The MIS is the system of record for what an import brings in (name, gender, age, county and the
enrolment status). When an officer fixes one of those values here, the fix is kept as a
``ParticipantCorrection`` so that:

* it can be listed and exported for whoever updates the MIS;
* a later import cannot silently overwrite it. If the import carries the corrected value the
  correction closes by itself (the MIS caught up); if it carries a different value the import is
  held back for that field and the conflict is shown to a reviewer.

Only youth that came from the MIS (an enrolment with a source number) are tracked: for anyone else
there is no MIS record to correct."""

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.configuration import services as configuration

from .models import Participant, ParticipantCorrection, ParticipantEnrollment

# Model attribute on Participant -> the correction field it is tracked under.
PARTICIPANT_FIELDS = {
    "full_name_source": "full_name",
    "gender": "gender",
    "age_at_source": "age",
    "origin_county_id": "county",
}
LABELS = dict(ParticipantCorrection.FIELDS)
OPEN = ParticipantCorrection.OPEN


class CorrectionError(Exception):
    def __init__(self, field, message, code="invalid"):
        super().__init__(message)
        self.field, self.message, self.code = field, message, code


def _raw(field, value) -> str:
    """The comparable form of a value: what the import will compare it with."""
    if value is None:
        return ""
    return str(value).strip().casefold() if field == "full_name" else str(value).strip()


def _label(field, value, counties=None) -> str:
    if value in (None, ""):
        return ""
    if field == "county":
        row = (counties or configuration.references_by_id("counties", [value])).get(str(value))
        return row.name if row else str(value)
    return str(value).capitalize() if field in ("gender", "status") else str(value)


def is_mis_record(p: Participant) -> bool:
    return p.enrollments.exclude(source_enrollment_no="").exists()


def _open(p, field, enrollment=None):
    return ParticipantCorrection.objects.filter(
        participant=p, field=field, enrollment=enrollment, state=OPEN
    ).first()


@transaction.atomic
def record(*, actor, participant, changes, enrollment=None):
    """Note officer edits to MIS-owned values. ``changes`` maps a tracked field name to
    ``(old, new)``. Returns the corrections touched.

    A second edit of the same value updates the open correction and keeps the original MIS value
    as its "was". Putting the value back to what the MIS had withdraws the correction."""
    if not changes or not is_mis_record(participant):
        return []
    ids = [v for f, (a, b) in changes.items() if f == "county" for v in (a, b) if v]
    counties = configuration.references_by_id("counties", ids) if ids else {}
    touched = []
    for field, (old, new) in changes.items():
        if _raw(field, old) == _raw(field, new):
            continue  # only the capitals of a name changed: nothing for the MIS to learn
        open_row = _open(participant, field, enrollment)
        if open_row and _raw(field, new) == open_row.before_raw:
            open_row.delete()  # back to what the MIS holds, nothing to tell it
            continue
        if open_row:
            open_row.after_raw = _raw(field, new)
            open_row.after_label = _label(field, new, counties)
            open_row.created_by = actor
            open_row.conflict_raw = open_row.conflict_label = open_row.conflict_batch = ""
            open_row.conflict_at = None
            open_row.save()
            touched.append(open_row)
            continue
        touched.append(
            ParticipantCorrection.objects.create(
                participant=participant,
                enrollment=enrollment,
                field=field,
                before_raw=_raw(field, old),
                before_label=_label(field, old, counties),
                after_raw=_raw(field, new),
                after_label=_label(field, new, counties),
                created_by=actor,
            )
        )
    return touched


def guard_import(participant, enrollment, incoming: dict, *, batch_ref: str) -> set[str]:
    """Which fields an import may not overwrite (R-15, D-005).

    ``incoming`` maps each field the file supplies a usable value for to that value. For every
    open correction: the same value closes it (the MIS caught up) and the write is harmless; a
    different value is held back and recorded on the correction for a reviewer. Returns the
    held-back field names."""
    held = set()
    now = timezone.now()
    rows = ParticipantCorrection.objects.filter(participant=participant, state=OPEN)
    for row in rows:
        if row.field not in incoming or (row.enrollment_id and row.enrollment_id != enrollment.pk):
            continue
        value = incoming[row.field]
        if _raw(row.field, value) == row.after_raw:
            row.state = ParticipantCorrection.CONFIRMED
            row.closed_how, row.closed_at = "mis_matched", now
            row.save()
            continue
        held.add(row.field)
        row.conflict_raw = _raw(row.field, value)
        row.conflict_label = _label(row.field, value)
        row.conflict_batch = batch_ref[:64]
        row.conflict_at = now
        row.save()
    return held


def _apply(row: ParticipantCorrection) -> None:
    """Write the MIS value that an import tried to bring in over the corrected one."""
    p = row.participant
    value = row.conflict_raw
    if row.field == "status":
        e = row.enrollment or ParticipantEnrollment.objects.filter(participant=p).first()
        if e:
            e.status = value
            e.save()
        return
    if row.field == "full_name":
        p.full_name_source = row.conflict_label
    elif row.field == "gender":
        p.gender = value
    elif row.field == "age":
        p.age_at_source = int(value)
    elif row.field == "county":
        p.origin_county_id = value or None
    p.save()


ACTIONS = ("confirm", "keep", "accept")


@transaction.atomic
def resolve(*, actor, correction, action, note=""):
    """A reviewer's decision on one open correction.

    ``confirm``: the MIS has been updated with the fix, so the guard is released.
    ``keep``: the import's different value is turned down; the fix stays and stays protected.
    ``accept``: the MIS value is right after all, so it replaces the fix and the fix closes."""
    c = ParticipantCorrection.objects.select_for_update().get(pk=correction.pk)
    if c.state != OPEN:
        raise CorrectionError("state", "This correction is already closed.", "closed")
    if action not in ACTIONS:
        raise CorrectionError("action", "Choose confirm, keep or accept.", "invalid")
    if action in ("keep", "accept") and not c.conflict_at:
        raise CorrectionError("action", "No import has disagreed with this fix.", "no_conflict")
    now = timezone.now()
    if action == "keep":
        c.conflict_raw = c.conflict_label = c.conflict_batch = ""
        c.conflict_at = None
        c.closed_note = note
        c.save()
    else:
        if action == "accept":
            _apply(c)
        c.state = ParticipantCorrection.CONFIRMED if action == "confirm" else "closed"
        c.closed_by, c.closed_at, c.closed_how, c.closed_note = actor, now, action, note
        c.save()
    audit.record(
        actor=actor,
        action="correction.resolved",
        object_type="participant",
        object_id=c.participant_id,
        after={"correction": str(c.pk), "field": c.field, "decision": action},
        reason=note,
    )
    return c


# --- listing and export ------------------------------------------------------------------------

STATE_FILTERS = ("open", "conflict", "confirmed", "closed", "all")


def filtered(user, params):
    """Corrections the caller may see (same scope as the youth table), under ``params``:
    ``state`` (open by default; ``conflict`` is open ones an import disagreed with) and ``q``
    (part of a name). A bad state is a ``ValueError``."""
    state = params.get("state") or "open"
    if state not in STATE_FILTERS:
        raise ValueError("Unknown state.")
    qs = ParticipantCorrection.objects.filter(
        participant__in=Participant.objects.visible_to(user, archived=None)
    )
    if state == "conflict":
        qs = qs.filter(state=OPEN, conflict_at__isnull=False)
    elif state != "all":
        qs = qs.filter(state=state)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(participant__full_name_source__icontains=q)
    return (
        qs.select_related("participant", "enrollment__programme", "created_by")
        .prefetch_related("participant__enrollments__programme")
        .order_by("-updated_at", "pk")
    )


def _mis_enrolment(c):
    if c.enrollment_id:
        return c.enrollment
    rows = [e for e in c.participant.enrollments.all() if e.source_enrollment_no]
    return rows[0] if rows else None


def out(c) -> dict:
    e = _mis_enrolment(c)
    return {
        "id": str(c.pk),
        "participant": {"id": str(c.participant_id), "name": c.participant.full_name_source},
        "field": c.field,
        "field_label": LABELS.get(c.field, c.field),
        "was": c.before_label,
        "now": c.after_label,
        "state": c.state,
        "state_label": dict(ParticipantCorrection.STATES)[c.state],
        "enrollment_no": e.source_enrollment_no if e else "",
        "programme": e.programme.name if e else "",
        "corrected_by": c.created_by.get_username() if c.created_by_id else "",
        "corrected_at": c.updated_at.isoformat(),
        "conflict": {
            "value": c.conflict_label,
            "batch": c.conflict_batch,
            "at": c.conflict_at.isoformat(),
        }
        if c.conflict_at and c.state == OPEN
        else None,
        "closed_how": c.closed_how,
        "closed_note": c.closed_note,
    }


EXPORT_GETTERS = {
    "name": lambda c, o: c.participant.full_name_source,
    "enrollment_no": lambda c, o: o["enrollment_no"],
    "programme": lambda c, o: o["programme"],
    "field": lambda c, o: o["field_label"],
    "was": lambda c, o: o["was"],
    "now": lambda c, o: o["now"],
    "corrected_on": lambda c, o: timezone.localtime(c.updated_at).date().isoformat(),
    "corrected_by": lambda c, o: o["corrected_by"],
    "state": lambda c, o: o["state_label"],
    "mis_value": lambda c, o: o["conflict"]["value"] if o["conflict"] else "",
}


def export_rows(user, params, keys) -> list[dict]:
    """One row per correction, ordered for whoever updates the MIS: by programme and number."""
    rows = []
    for c in filtered(user, params):
        o = out(c)
        rows.append({k: EXPORT_GETTERS[k](c, o) for k in keys if k in EXPORT_GETTERS})
    return sorted(rows, key=lambda r: (r.get("programme", ""), r.get("enrollment_no", "")))
