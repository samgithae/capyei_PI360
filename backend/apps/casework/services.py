"""Case management (T-064 work queue, T-065 placements and episodes).

A coordination module, like the youth portal: it has no tables of its own. It puts the record
scope (which youth the caller may see) in front of the placement history, and gathers the
officer's work queue from interventions, referrals, flags and placements, each of which stays
inside its own module."""

import uuid
from datetime import date

from django.utils import timezone

from apps.api.access import has_permission
from apps.audit import services as audit
from apps.employers import services as employers
from apps.intelligence import services as intelligence
from apps.participants import services as participants
from apps.placements import services as placements
from apps.referrals import services as referrals

PATHWAY_NAMES = dict(placements.Placement.PATHWAYS)
FOLLOWUP_KINDS = dict(placements.FollowUpStep.KINDS)
FOLLOWUP_STATUSES = dict(placements.FollowUp.STATUSES)
FOLLOWUP_METHODS = dict(placements.FollowUpAttempt.METHODS)
FOLLOWUP_OUTCOMES = dict(placements.FollowUp.OUTCOMES)
SOURCE_NAMES = dict(placements.Placement.SOURCES)
OPERATIONAL_NAMES = dict(placements.Placement.OPERATIONAL_STATUSES)
# Self-employment income is economic data (G9, D-090 pending): grant-only, never by role.
INCOME_PERMISSION = "restricted.view_background"
FLAG_LIMIT = 10
FOLLOWUP_LIMIT = 50


class NotFound(Exception):
    pass


class Violation(Exception):
    """A rule the request broke; shown next to the field."""

    def __init__(self, field, message, code="invalid"):
        super().__init__(message)
        self.field, self.message, self.code = field, message, code


# --- placements ------------------------------------------------------------------------------


def _owners(user) -> dict:
    """``{enrollment id: participant id}`` for youth inside the user's scope."""
    return participants.enrollment_owners(user)


def _row(p, names: dict, owners: dict, types: dict | None = None) -> dict:
    pid = owners.get(p.enrollment_id)
    type_id = str(p.employment_type_id) if p.employment_type_id else None
    return {
        "id": str(p.pk),
        "participant_id": str(pid) if pid else None,
        "participant": names.get(pid, ""),
        "enrollment_id": str(p.enrollment_id),
        "employer_id": str(p.employer_id) if p.employer_id else None,
        "employer": p.employer.name if p.employer_id else p.employer_name_source,
        "linked": p.employer_id is not None,
        "designation": p.designation,
        "pathway": p.pathway,
        "pathway_label": PATHWAY_NAMES.get(p.pathway, ""),
        "status": p.status,
        "source_status": p.source_status,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "exit_reason": p.exit_reason,
        "current": placements.is_current(p),
        "verified": p.verified_on is not None,
        "verified_on": p.verified_on.isoformat() if p.verified_on else None,
        "verification_source": p.verification_source,
        "verification_source_label": SOURCE_NAMES.get(p.verification_source, ""),
        "imported": p.source_row_id is not None,
        # NEW-071: the self-employment outcome's own facts (business name is "employer").
        "business_activity": p.business_activity,
        "operational_status": p.operational_status,
        "operational_status_label": OPERATIONAL_NAMES.get(p.operational_status, ""),
        "business_evidence": p.business_evidence,
        # NEW-035: the employment type (B25), shown to everyone who sees the placement.
        "employment_type_id": type_id,
        "employment_type": (types or {}).get(type_id, "") if type_id else "",
    }


def rows_for(user, placement_list, owners=None) -> list[dict]:
    owners = _owners(user) if owners is None else owners
    pids = {owners.get(p.enrollment_id) for p in placement_list} - {None}
    names = participants.names(pids)
    types = {}
    if any(p.employment_type_id for p in placement_list):
        types = {
            r["id"]: r["name"]
            for r in placements.outcome_list("employment-types", include_inactive=True)
        }
    given = placements.with_exit_feedback([p.pk for p in placement_list])
    return [
        {**_row(p, names, owners, types), "exit_feedback_given": p.pk in given}
        for p in placement_list
    ]


def list_placements(user, *, pathway="", state="", employer_id=None, q="", participant_id=None,
                    offset=0, size: int | None = 25) -> tuple[int, list[dict]]:  # fmt: skip
    owners = _owners(user)
    if participant_id:
        enrollments = [e for e, pid in owners.items() if str(pid) == str(participant_id)]
    else:
        enrollments = list(owners)
    name_hits = participants.matching_ids(user, q) if q else set()
    qs = placements.list_for(
        enrollments, pathway=pathway, state=state, employer_id=employer_id, q=q,
        q_enrollment_ids=[e for e, pid in owners.items() if pid in name_hits],
    )  # fmt: skip
    total = qs.count()
    page = qs[offset : offset + size] if size else qs
    return total, rows_for(user, list(page), owners)


PLACEMENT_STATES = ("current", "ended", "unverified")
FOLLOWUP_STATES = ("open", "overdue", "due_soon", "done", "closed", "all")


def _uuid_or_none(value):
    return uuid.UUID(value) if value else None


def placement_filters(params) -> dict:
    """The placements list's filters as keyword arguments. A bad id raises ``ValueError``."""
    return {
        "pathway": params.get("pathway") if params.get("pathway") in PATHWAY_NAMES else "",
        "state": params.get("state") if params.get("state") in PLACEMENT_STATES else "",
        "employer_id": _uuid_or_none(params.get("employer")),
        "q": params.get("q", "").strip(),
        "participant_id": _uuid_or_none(params.get("participant")),
    }


def followup_filters(user, params) -> dict:
    """The follow-ups list's filters as keyword arguments. A bad id raises ``ValueError``."""
    return {
        "state": params.get("state") if params.get("state") in FOLLOWUP_STATES else "open",
        "kind": params.get("kind") if params.get("kind") in FOLLOWUP_KINDS else "",
        "mine": params.get("mine") == "1",
        "q": params.get("q", "").strip(),
        "participant_id": _uuid_or_none(params.get("participant")),
        "placement_id": _uuid_or_none(params.get("placement")),
    }


def export_placements(user, params, keys=None) -> list[dict]:
    """Placements as plain rows for an export. No notes or evidence files."""
    _, rows = list_placements(user, size=None, **placement_filters(params))
    return [
        {
            "youth": r["participant"],
            "employer": r["employer"],
            "designation": r["designation"],
            "pathway": r["pathway_label"],
            "state": "Current" if r["current"] else "Ended" if r["end_date"] else "Not current",
            "start_date": r["start_date"] or "",
            "end_date": r["end_date"] or "",
            "exit_reason": r["exit_reason"],
            "verified": "Yes" if r["verified"] else "No",
            "verified_on": r["verified_on"] or "",
            "verification_source": r["verification_source_label"],
            "imported": "Yes" if r["imported"] else "No",
        }
        for r in rows
    ]


def youth_placements(user, participant_ids) -> dict:
    """``{youth id: ["Role at Employer: Pathway, state", ...]}`` for the youth export, limited to
    the placements the user may see."""
    wanted = {str(i) for i in participant_ids}
    out: dict = {}
    _, rows = list_placements(user, size=None)
    for r in rows:
        if r["participant_id"] in wanted:
            state = "current" if r["current"] else "ended" if r["end_date"] else "not current"
            role = r["designation"] or "Placement"
            what = f"{role} at {r['employer']}: {r['pathway_label']}, {state}"
            out.setdefault(uuid.UUID(r["participant_id"]), []).append(what)
    return out


def export_followups(user, params, keys=None) -> list[dict]:
    """Follow-ups as plain rows for an export. No response notes."""
    _, rows = list_followups(user, size=None, **followup_filters(user, params))
    return [
        {
            "youth": r["participant"],
            "employer": r["employer"],
            "designation": r["designation"],
            "placement_start": r["placement_start"] or "",
            "follow_up": r["label"] or r["kind_label"],
            "kind": r["kind_label"],
            "due_date": r["due_date"],
            "status": "Overdue" if r["overdue"] else r["status_label"],
            "assigned_to": r["assigned_to"] or "",
            "attempts": r["attempts"] if r["attempts"] is not None else "",
            "next_action": r["next_action"] or "",
            "next_action_date": r["next_action_date"] or "",
        }
        for r in rows
    ]


def summary(user) -> dict:
    enrollments = list(_owners(user))
    out = {
        "total": placements.list_for(enrollments).count(),
        "current": placements.list_for(enrollments, state="current").count(),
        "ended": placements.list_for(enrollments, state="ended").count(),
        "unverified": placements.list_for(enrollments, state="unverified").count(),
        "by_pathway": {},
    }
    for code, label in placements.Placement.PATHWAYS:
        out["by_pathway"][code] = {
            "label": label,
            "current": placements.list_for(enrollments, pathway=code, state="current").count(),
        }
    return out


def get_placement(user, placement_id):
    """The episode, if its youth is inside the user's scope; otherwise NotFound."""
    try:
        p = placements.get(placement_id)
    except placements.PlacementError:
        raise NotFound from None
    if p.enrollment_id not in _owners(user):
        raise NotFound
    return p


def detail(user, p, *, can_edit: bool) -> dict:
    row = rows_for(user, [p])[0]
    income = can_see_income(user)
    return {
        **row,
        "benefits": p.benefits,
        # Shown only to a holder of the grant; others see neither the amount nor whether it exists.
        "monthly_income": (
            str(p.monthly_income) if income and p.monthly_income is not None else None
        ),
        # The salary and its band are economic data too (A3): the same grant.
        "salary_amount": str(p.salary_amount) if income and p.salary_amount is not None else None,
        "salary_band_id": str(p.salary_band_id) if income and p.salary_band_id else None,
        "salary_band": (
            placements.outcome_name("salary-bands", p.salary_band_id) if income else ""
        ),
        "exit_feedback": _exit_feedback(user, p.pk),
        "can": {
            "income": income,
            "edit": can_edit and not row["imported"],
            "end": can_edit and p.end_date is None,
            "exit_feedback": can_edit
            and p.end_date is not None
            and not placements.exit_feedback_of(p.pk),
            "verify": can_edit,
        },
    }


def history(placement) -> list[dict]:
    return audit.history("placement", placement.pk)


def _wrap(call, **kwargs):
    try:
        return call(**kwargs)
    except placements.FollowUpError as exc:
        raise Violation(exc.field, exc.message, exc.code) from exc
    except placements.ActivePlacementExists as exc:
        raise Violation("", str(exc), "active_placement") from exc
    except placements.PlacementError as exc:
        raise Violation("", str(exc)) from exc


def _check_employer(employer_id):
    if employer_id and not employers.exists(employer_id):
        raise Violation("employer_id", "Employer not found.", "unknown_employer")


def _enrollment_for(user, participant_id, enrollment_id):
    if not participants.is_visible(user, participant_id):
        raise Violation("participant_id", "Youth not found.", "unknown_participant")
    own = [str(e) for e in participants.enrollment_ids(participant_id)]
    if enrollment_id:
        if str(enrollment_id) not in own:
            raise Violation(
                "enrollment_id", "That enrollment is not this youth's.", "bad_enrollment"
            )
        return enrollment_id
    if len(own) == 1:
        return own[0]
    if not own:
        raise Violation("enrollment_id", "This youth has no enrollment yet.", "no_enrollment")
    raise Violation(
        "enrollment_id", "Choose which enrollment this belongs to.", "choose_enrollment"
    )


def enrollment_choices(user, participant_id) -> list:
    if not participants.is_visible(user, participant_id):
        raise NotFound
    return [str(e) for e in participants.enrollment_ids(participant_id)]


def can_see_income(user) -> bool:
    return has_permission(user, INCOME_PERMISSION)


ECONOMIC_FIELDS = ("monthly_income", "salary_amount", "salary_band_id")


def _check_income(actor, fields: dict):
    """Writing the income, salary or band (even clearing one) needs the grant; the backend
    enforces it."""
    given = [f for f in ECONOMIC_FIELDS if f in fields]
    if given and not can_see_income(actor):
        raise Violation(
            given[0], "You need the restricted economic-data grant to record income or salary.",
            "forbidden",
        )  # fmt: skip


def create_placement(*, actor, participant_id, enrollment_id=None, employer_id=None, **fields):
    """D-081 (PI360-NEW-070): refused while the youth has a running placement; the officer ends
    it first or uses Changed employer. An episode entered with its end date is history and is
    always allowed."""
    _check_income(actor, fields)
    _check_employer(employer_id)
    enrollment = _enrollment_for(actor, participant_id, enrollment_id)
    return _wrap(
        placements.record_manual, actor=actor, enrollment_id=enrollment,
        employer_id=employer_id, **fields,
    )  # fmt: skip


def update_placement(*, actor, placement, **changes):
    _check_income(actor, changes)
    if changes.get("employer_id"):
        _check_employer(changes["employer_id"])
    return _wrap(placements.update_episode, actor=actor, placement_id=placement.pk, **changes)


def end_placement(*, actor, placement, end_date, exit_reason=""):
    return _wrap(
        placements.end_episode, actor=actor, placement_id=placement.pk, end_date=end_date,
        exit_reason=exit_reason,
    )  # fmt: skip


def record_exit_feedback(*, actor, placement, rating, comment="", assisted=True, given_on=None):
    """NEW-039/076: whether the comment is confidential is decided here from the admin default
    and stored on the record, so a later change of the default touches new feedback only."""
    confidential = bool(intelligence.setting("exit.confidential_default"))
    return _wrap(
        placements.record_exit_feedback, actor=actor, placement_id=placement.pk, rating=rating,
        comment=comment, assisted=assisted, confidential=confidential, given_on=given_on,
    )  # fmt: skip


def _exit_feedback(user, placement_id):
    fb = placements.exit_feedback_of(placement_id)
    if fb is None:
        return None
    hidden = fb.confidential and not has_permission(user, "placements.view_exit_comments")
    return {
        "rating": fb.rating,
        "comment": "" if hidden else fb.comment,
        "comment_hidden": hidden and bool(fb.comment),
        "confidential": fb.confidential,
        "assisted": fb.assisted,
        "given_on": fb.given_on.isoformat(),
    }


def change_employer(*, actor, placement, employer_id=None, **fields):
    _check_income(actor, fields)
    _check_employer(employer_id)
    return _wrap(
        placements.change_employer, actor=actor, placement_id=placement.pk,
        employer_id=employer_id, **fields,
    )  # fmt: skip


def verify_placement(*, actor, placement, source):
    return _wrap(placements.verify_episode, actor=actor, placement_id=placement.pk, source=source)


# --- follow-ups (T-066, FR-25/FR-26) -------------------------------------------------------------


def _person(u) -> str:
    return (u.get_full_name() or u.get_username()) if u else ""


def _followup_row(f, names: dict, owners: dict, today: date) -> dict:
    p = f.placement
    pid = owners.get(p.enrollment_id)
    return {
        "id": str(f.pk),
        "participant_id": str(pid) if pid else None,
        "participant": names.get(pid, ""),
        "placement_id": str(p.pk),
        "employer": p.employer.name if p.employer_id else p.employer_name_source,
        "designation": p.designation,
        "placement_start": p.start_date.isoformat() if p.start_date else None,
        "placement_ended": p.end_date is not None,
        "kind": f.kind,
        "kind_label": FOLLOWUP_KINDS[f.kind],
        "label": f.label,
        "due_date": f.due_date.isoformat(),
        "status": f.status,
        "status_label": FOLLOWUP_STATUSES[f.status],
        "overdue": placements.followup_is_overdue(f, today),
        "assigned_to_id": f.assigned_to_id,
        "assigned_to": _person(f.assigned_to),
        "next_action": f.next_action,
        "next_action_date": f.next_action_date.isoformat() if f.next_action_date else None,
        "attempts": getattr(f, "attempt_count", None),
    }


def followup_rows(user, rows, owners=None, today=None) -> list[dict]:
    owners = _owners(user) if owners is None else owners
    today = today or timezone.localdate()
    pids = {owners.get(f.placement.enrollment_id) for f in rows} - {None}
    names = participants.names(pids)
    return [_followup_row(f, names, owners, today) for f in rows]


def list_followups(user, *, state="open", kind="", mine=False, q="", participant_id=None,
                   placement_id=None, offset=0, size: int | None = 25):  # fmt: skip
    owners = _owners(user)
    today = timezone.localdate()
    if participant_id:
        enrollments = [e for e, pid in owners.items() if str(pid) == str(participant_id)]
    else:
        enrollments = list(owners)
    narrowed = None
    if q:
        hits = participants.matching_ids(user, q)
        narrowed = [e for e, pid in owners.items() if pid in hits]
    qs = placements.followup_list(
        enrollments, state=state, kind=kind, assigned_to=user.pk if mine else None,
        placement_id=placement_id, q_enrollment_ids=narrowed, today=today,
    )  # fmt: skip
    total = qs.count()
    page = qs[offset : offset + size] if size else qs
    return total, followup_rows(user, list(page), owners, today)


def followup_summary(user, *, mine: bool = False) -> dict:
    return placements.followup_counts(list(_owners(user)), assigned_to=user.pk if mine else None)


def get_followup(user, followup_id):
    """The follow-up, if its youth is inside the user's scope; otherwise NotFound."""
    try:
        f = placements.followup_get(followup_id)
    except placements.PlacementError:
        raise NotFound from None
    if f.placement.enrollment_id not in _owners(user):
        raise NotFound
    return f


def followup_detail(user, f, *, can_edit: bool, can_assign: bool) -> dict:
    row = followup_rows(user, [f])[0]
    live = f.status == placements.FollowUp.OPEN
    return {
        **row,
        "response_note": f.response_note,
        "still_employed": f.still_employed,
        # NEW-034: what the check-in found. Blank outcome = recorded before NEW-034.
        "outcome": f.outcome,
        "outcome_label": FOLLOWUP_OUTCOMES.get(f.outcome, ""),
        "leaving_reason_id": str(f.leaving_reason_id) if f.leaving_reason_id else None,
        "leaving_reason": placements.outcome_name("leaving-reasons", f.leaving_reason_id),
        "left_on": f.left_on.isoformat() if f.left_on else None,
        "observations": f.observations,
        "new_placement_id": str(f.new_placement_id) if f.new_placement_id else None,
        "evidence_source": f.evidence_source,
        "evidence_source_label": SOURCE_NAMES.get(f.evidence_source, ""),
        "closed_at": f.closed_at.isoformat() if f.closed_at else None,
        "closed_by": _person(f.closed_by) if f.closed_by_id else "",
        "attempt_list": [
            {
                "id": str(a.pk),
                "method": a.method,
                "method_label": FOLLOWUP_METHODS[a.method],
                "reached": a.reached,
                "made_on": a.made_on.isoformat(),
                "note": a.note,
                "made_by": _person(a.made_by),
            }
            for a in placements.followup_attempts(f)
        ],
        "can": {"work": can_edit and live, "assign": can_assign and live},
    }


def followup_history(f) -> list[dict]:
    return placements.followup_history(f)


def log_attempt(*, actor, followup, **fields):
    return _wrap(placements.followup_log_attempt, actor=actor, followup_id=followup.pk, **fields)


def complete_followup(*, actor, followup, **fields):
    """The new work recorded from a follow-up follows the same salary rule as a placement."""
    _check_income(actor, fields.get("new_job") or {})
    if (fields.get("new_job") or {}).get("employer_id"):
        _check_employer(fields["new_job"]["employer_id"])
    return _wrap(placements.followup_complete, actor=actor, followup_id=followup.pk, **fields)


def unreachable_followup(*, actor, followup, note=""):
    return _wrap(placements.followup_unreachable, actor=actor, followup_id=followup.pk, note=note)


def cancel_followup(*, actor, followup, reason):
    return _wrap(placements.followup_cancel, actor=actor, followup_id=followup.pk, reason=reason)


def assign_followup(*, actor, followup, owner_id, note=""):
    return _wrap(
        placements.followup_assign, actor=actor, followup_id=followup.pk, owner_id=owner_id,
        note=note,
    )  # fmt: skip


def schedule_steps() -> list[dict]:
    return [
        {
            "id": str(s.pk),
            "kind": s.kind,
            "kind_label": FOLLOWUP_KINDS[s.kind],
            "label": s.label,
            "offset_days": s.offset_days,
            "active": s.active,
        }
        for s in placements.followup_steps()
    ]


def create_schedule_step(*, actor, **fields):
    return _wrap(placements.followup_create_step, actor=actor, **fields)


def update_schedule_step(*, actor, step_id, **changes):
    return _wrap(placements.followup_update_step, actor=actor, step_id=step_id, **changes)


# --- the work queue (FR-22) ----------------------------------------------------------------------


def queue(user, *, mine: bool, today: date | None = None) -> dict:
    """What needs doing, in one place: interventions (overdue first), referrals waiting on staff,
    flagged youth and placements nobody has verified. ``mine`` limits interventions and
    referrals to those assigned to the user; flags and placements follow the user's scope."""
    today = today or timezone.localdate()
    now = timezone.now()
    counts = referrals.counts_for(user, mine=mine, today=today)
    waiting_total, waiting = referrals.queue_referrals(user, mine=mine, now=now)
    out = {
        "scope": "mine" if mine else "all",
        "today": today.isoformat(),
        "counts": {**counts, "referrals_waiting": waiting_total},
        "interventions": referrals.queue_interventions(user, mine=mine, today=today),
        "referrals": waiting,
        "flags": None,
        "placements_to_verify": None,
        "followups": None,
    }
    if has_permission(user, "intelligence.view"):
        ids = participants.visible_ids(user).values_list("pk", flat=True)
        q = intelligence.support_queue(ids, today, limit=FLAG_LIMIT)
        out["flags"] = {"total": q["counts"]["flagged"], "items": q["items"]}
        out["counts"]["flagged"] = q["counts"]["flagged"]
    if has_permission(user, "placements.view"):
        owners = _owners(user)
        n = placements.unverified_count(list(owners))
        out["placements_to_verify"] = n
        out["counts"]["placements_to_verify"] = n
        due = placements.followup_list(
            list(owners), state="open", assigned_to=user.pk if mine else None, today=today
        )
        due_rows = list(due[:FOLLOWUP_LIMIT])
        out["followups"] = followup_rows(user, due_rows, owners, today)
        fc = placements.followup_counts(list(owners), assigned_to=user.pk if mine else None,
                                        today=today)  # fmt: skip
        out["counts"]["followups_open"] = fc["open"]
        out["counts"]["followups_overdue"] = fc["overdue"]
        out["counts"]["followups_due_soon"] = fc["due_soon"]
    return out
