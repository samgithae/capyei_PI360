"""Follow-up scheduling (T-066, FR-25/FR-26, BR-10). Re-exported by ``apps.placements.services``;
other modules call these as ``placements.<name>``.

The schedule is data (``FollowUpStep``). When a placement is confirmed, each active step becomes a
``FollowUp`` task that keeps its own copy of the label and due date, so a later change to the
schedule only affects placements confirmed after it. A task is never deleted: stop one by
cancelling it. Every change is audited in the same transaction; audit rows hold field values and
ids, never the free text staff type."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.api.access import has_permission
from apps.audit import services as audit
from apps.configuration import services as configuration

from .models import FollowUp, FollowUpAttempt, FollowUpStep, Placement
from .services import PLACED, SOURCES, PlacementError

KINDS = dict(FollowUpStep.KINDS)
METHODS = dict(FollowUpAttempt.METHODS)
OUTCOMES = dict(FollowUp.OUTCOMES)
STATUSES = dict(FollowUp.STATUSES)
DUE_SOON_DAYS = 7
# A step already this far past its due date when the tasks are generated is skipped: confirming
# an old placement should not bury the officer in check-ins nobody can do on time any more.
STALE_AFTER_DAYS = 30
# Who may be given a follow-up: an active user who works cases.
WORKER_PERMISSION = "referrals.edit"


class FollowUpError(PlacementError):
    """A rule the request broke. ``field`` names the form field it belongs to ('' for none)."""

    def __init__(self, field, message, code="invalid"):
        super().__init__(message)
        self.field, self.message, self.code = field, message, code


def _text(field, value, *, label, limit, required=False):
    value = (value or "").strip()
    if required and not value:
        raise FollowUpError(field, f"Say {label}.", "required")
    if len(value) > limit:
        raise FollowUpError(field, f"Keep {label} under {limit} characters.", "too_long")
    return value


def _snapshot(f: FollowUp) -> dict:
    return {
        "placement": str(f.placement_id),
        "kind": f.kind,
        "label": f.label,
        "due_date": f.due_date.isoformat(),
        "status": f.status,
        "assigned_to": f.assigned_to_id,
        "still_employed": f.still_employed,
        # NEW-034. The observations are free text and stay out of the audit trail.
        "outcome": f.outcome,
        "leaving_reason": str(f.leaving_reason_id) if f.leaving_reason_id else None,
        "left_on": f.left_on.isoformat() if f.left_on else None,
        "new_placement": str(f.new_placement_id) if f.new_placement_id else None,
        "evidence_source": f.evidence_source,
        "next_action_date": f.next_action_date.isoformat() if f.next_action_date else None,
    }


def is_overdue(f: FollowUp, today: date) -> bool:
    return f.status == FollowUp.OPEN and f.due_date < today


# --- the schedule ---------------------------------------------------------------------------------


def steps() -> list[FollowUpStep]:
    return list(FollowUpStep.objects.all())


def _check_step(*, kind, label, offset_days, active, ignore_id=None):
    if kind not in KINDS:
        raise FollowUpError("kind", "Choose early or tracer.", "unknown_kind")
    label = _text("label", label, label="the name of this step", limit=60, required=True)
    if not isinstance(offset_days, int) or not 1 <= offset_days <= FollowUpStep.MAX_DAYS:
        raise FollowUpError(
            "offset_days",
            f"Give a number of days from 1 to {FollowUpStep.MAX_DAYS} (24 months).",
            "bad_offset",
        )
    clash = FollowUpStep.objects.filter(offset_days=offset_days, active=True)
    if ignore_id:
        clash = clash.exclude(pk=ignore_id)
    if active and clash.exists():
        raise FollowUpError(
            "offset_days", "Another active step already falls on that day.", "duplicate_offset"
        )
    return label


def _step_snapshot(s: FollowUpStep) -> dict:
    return {"kind": s.kind, "label": s.label, "offset_days": s.offset_days, "active": s.active}


@transaction.atomic
def create_step(*, actor, kind, label, offset_days, active=True) -> FollowUpStep:
    label = _check_step(kind=kind, label=label, offset_days=offset_days, active=active)
    s = FollowUpStep.objects.create(kind=kind, label=label, offset_days=offset_days, active=active)
    audit.record(
        actor=actor, action="followup_step.created", object_type="followup_step",
        object_id=s.pk, after=_step_snapshot(s),
    )  # fmt: skip
    return s


@transaction.atomic
def update_step(*, actor, step_id, **changes) -> FollowUpStep:
    """Change a step. Tasks already generated keep what they were given (FR-25)."""
    try:
        s = FollowUpStep.objects.select_for_update().get(pk=step_id)
    except (FollowUpStep.DoesNotExist, ValueError, TypeError):
        raise FollowUpError("", "That step does not exist.", "unknown") from None
    before = _step_snapshot(s)
    merged = {**before, **{k: v for k, v in changes.items() if k in before}}
    label = _check_step(ignore_id=s.pk, **merged)
    s.kind, s.label, s.offset_days, s.active = (
        merged["kind"], label, merged["offset_days"], merged["active"],
    )  # fmt: skip
    s.save()
    audit.record(
        actor=actor, action="followup_step.updated", object_type="followup_step",
        object_id=s.pk, before=before, after=_step_snapshot(s),
    )  # fmt: skip
    return s


# --- generating tasks -----------------------------------------------------------------------------


@transaction.atomic
def generate_for(placement: Placement, *, actor, today: date | None = None) -> list[FollowUp]:
    """Make a task for each active step that has none yet for this placement. Needs a running
    'placed' episode with a start date. Safe to call again: it only fills what is missing, and
    never touches a task that exists (so a changed schedule affects new placements only)."""
    if placement.status != PLACED or placement.start_date is None or placement.end_date:
        return []
    today = today or timezone.localdate()
    have = set(placement.followups.values_list("step_id", flat=True))
    made = []
    for step in FollowUpStep.objects.filter(active=True):
        if step.pk in have:
            continue
        due = placement.start_date + timedelta(days=step.offset_days)
        if due < today - timedelta(days=STALE_AFTER_DAYS):
            continue
        f = FollowUp.objects.create(
            placement=placement, step=step, kind=step.kind, label=step.label, due_date=due,
            assigned_to=actor if actor is not None and actor.is_authenticated else None,
        )  # fmt: skip
        audit.record(
            actor=actor, action="followup.created", object_type="followup",
            object_id=f.pk, after=_snapshot(f),
        )  # fmt: skip
        made.append(f)
    return made


# --- reading --------------------------------------------------------------------------------------


def get(followup_id) -> FollowUp:
    try:
        return FollowUp.objects.select_related("placement", "assigned_to").get(pk=followup_id)
    except (FollowUp.DoesNotExist, ValueError, TypeError):
        raise FollowUpError("", "That follow-up does not exist.", "unknown") from None


def attempts_of(followup: FollowUp) -> list[FollowUpAttempt]:
    return list(followup.attempts.select_related("made_by"))


def list_for(
    enrollment_ids, *, state="open", kind="", assigned_to=None, placement_id=None,
    q_enrollment_ids=None, today: date | None = None,
):  # fmt: skip
    """Follow-ups for the given enrollments (a queryset, soonest due first). ``state``: open,
    overdue, due_soon, done, closed (done, unreachable or cancelled) or all. ``q_enrollment_ids``,
    when given, narrows to those enrollments (a name search done by the caller)."""
    today = today or timezone.localdate()
    qs = FollowUp.objects.filter(placement__enrollment_id__in=list(enrollment_ids))
    if q_enrollment_ids is not None:
        qs = qs.filter(placement__enrollment_id__in=list(q_enrollment_ids))
    if kind in KINDS:
        qs = qs.filter(kind=kind)
    if assigned_to is not None:
        qs = qs.filter(assigned_to=assigned_to)
    if placement_id:
        qs = qs.filter(placement_id=placement_id)
    if state == "open":
        qs = qs.filter(status=FollowUp.OPEN)
    elif state == "overdue":
        qs = qs.filter(status=FollowUp.OPEN, due_date__lt=today)
    elif state == "due_soon":
        qs = qs.filter(
            status=FollowUp.OPEN, due_date__gte=today,
            due_date__lte=today + timedelta(days=DUE_SOON_DAYS),
        )  # fmt: skip
    elif state == "done":
        qs = qs.filter(status=FollowUp.DONE)
    elif state == "closed":
        qs = qs.exclude(status=FollowUp.OPEN)
    # an aggregate query ignores Meta.ordering, so the order is stated here
    return (
        qs.select_related("placement", "placement__employer", "assigned_to")
        .annotate(attempt_count=Count("attempts"))
        .order_by("due_date", "created_at")
    )


def counts(enrollment_ids, *, assigned_to=None, today: date | None = None) -> dict:
    """Headline numbers and the early/tracer split the TOR dashboard will read (FR-26)."""
    today = today or timezone.localdate()
    base = list_for(enrollment_ids, state="all", assigned_to=assigned_to, today=today)
    open_ = base.filter(status=FollowUp.OPEN)
    out = {
        "open": open_.count(),
        "overdue": open_.filter(due_date__lt=today).count(),
        "due_soon": open_.filter(
            due_date__gte=today, due_date__lte=today + timedelta(days=DUE_SOON_DAYS)
        ).count(),
        "done": base.filter(status=FollowUp.DONE).count(),
        "unreachable": base.filter(status=FollowUp.UNREACHABLE).count(),
        "by_kind": {},
    }
    for kind, label in FollowUpStep.KINDS:
        k = base.filter(kind=kind)
        out["by_kind"][kind] = {
            "label": label,
            "open": k.filter(status=FollowUp.OPEN).count(),
            "done": k.filter(status=FollowUp.DONE).count(),
        }
    return out


def facts() -> list[dict]:
    """One small dict per check-in on a placement that counts as placed, for the reports. A
    cancelled task is left out; an open or unreachable one is "due, not yet checked"."""
    rows = (
        FollowUp.objects.filter(placement__status=PLACED)
        .exclude(status=FollowUp.CANCELLED)
        .values_list(
            "pk",
            "placement_id",
            "placement__enrollment_id",
            "kind",
            "step__offset_days",
            "label",
            "due_date",
            "status",
            "still_employed",
            "outcome",
            "placement__previous_placement_id",
        )
    )
    return [
        {
            "id": r[0],
            "placement_id": r[1],
            "enrollment_id": r[2],
            "kind": r[3],
            "offset_days": r[4],
            "label": r[5],
            "due_date": r[6],
            "status": r[7],
            "still_employed": r[8],
            "outcome": r[9],
            # a first job, not one that followed a change of employer (the retention cohort)
            "root": r[10] is None,
        }
        for r in rows
    ]


# --- working a follow-up --------------------------------------------------------------------------


def retention_counts(employer_id, since: date, today: date) -> dict:
    """How many of an employer's placements were still going at the early retention point (D-028).

    The point is read from the schedule, never fixed here: it is the latest active early step
    (90 days by default), so an administrator who moves it moves this too. Counts the check-ins of
    that step that fell due from ``since`` to ``today``. Only a completed check-in counts as
    checked, and completing one needs an answer and a stated source, so every checked one is
    verified. Cancelled tasks are left out; an open or unreachable one is "due, not yet checked",
    never counted as lost."""
    early = list(
        FollowUpStep.objects.filter(kind=FollowUpStep.EARLY, active=True).values_list(
            "offset_days", flat=True
        )
    )
    if not early:
        return {"point_days": None, "due": 0, "checked": 0, "retained": 0}
    point = max(early)
    due = (
        FollowUp.objects.filter(
            placement__employer_id=employer_id,
            kind=FollowUpStep.EARLY,
            step__offset_days=point,
            due_date__gte=since,
            due_date__lte=today,
        )
        .exclude(status=FollowUp.CANCELLED)
    )  # fmt: skip
    checked = due.filter(status=FollowUp.DONE, still_employed__isnull=False)
    return {
        "point_days": point,
        "due": due.count(),
        "checked": checked.count(),
        "retained": checked.filter(still_employed=True).count(),
    }


def _locked_open(followup_id) -> FollowUp:
    try:
        f = FollowUp.objects.select_for_update().select_related("placement").get(pk=followup_id)
    except (FollowUp.DoesNotExist, ValueError, TypeError):
        raise FollowUpError("", "That follow-up does not exist.", "unknown") from None
    if f.status != FollowUp.OPEN:
        raise FollowUpError("status", "This follow-up is already closed.", "not_open")
    return f


def _close(f: FollowUp, *, actor, status):
    f.status, f.closed_at, f.closed_by = status, timezone.now(), actor
    f.next_action, f.next_action_date = "", None


@transaction.atomic
def log_attempt(
    *, actor, followup_id, method, reached, note="", made_on=None, next_action="",
    next_action_date=None,
) -> FollowUp:  # fmt: skip
    """Record one try at reaching the youth. The next action replaces the previous one."""
    f = _locked_open(followup_id)
    today = timezone.localdate()
    made_on = made_on or today
    if method not in METHODS:
        raise FollowUpError("method", "Choose how you tried to reach them.", "unknown_method")
    if made_on > today:
        raise FollowUpError("made_on", "The attempt cannot be in the future.", "future")
    if next_action_date is not None and next_action_date < today:
        raise FollowUpError("next_action_date", "The next step cannot be in the past.", "past")
    note = _text("note", note, label="the note", limit=2000)
    if not reached and not note:
        raise FollowUpError("note", "Say what happened (for example, no answer).", "required")
    before = _snapshot(f)
    FollowUpAttempt.objects.create(
        followup=f, method=method, reached=bool(reached), made_on=made_on, note=note, made_by=actor
    )
    f.next_action = _text("next_action", next_action, label="the next step", limit=200)
    f.next_action_date = next_action_date if f.next_action else None
    f.save()
    audit.record(
        actor=actor, action="followup.attempted", object_type="followup", object_id=f.pk,
        before=before, after={**_snapshot(f), "method": method, "reached": bool(reached)},
    )  # fmt: skip
    return f


def outcome_lists() -> dict:
    """What the follow-up form offers (NEW-034, B25): the outcomes and the active reasons."""
    return {
        "outcomes": [{"value": v, "label": label} for v, label in FollowUp.OUTCOMES],
        "leaving_reasons": configuration.outcome_list("leaving-reasons"),
    }


NEW_JOB_FIELDS = {
    "pathway", "start_date", "employer_id", "employer_name_source", "designation", "benefits",
    "employment_type_id", "salary_amount", "salary_band_id", *Placement.SELF_EMPLOYMENT_FIELDS,
}  # fmt: skip


def _as_followup_error(error: PlacementError, field: str) -> FollowUpError:
    if isinstance(error, FollowUpError):
        return error
    return FollowUpError(field, str(error), getattr(error, "code", "invalid"))


def _new_work(f, *, actor, outcome, running, left_on, new_job) -> Placement | None:
    """The job the youth now has (changed employer or self-employed), as a placement episode.
    A running placement is ended and the new one follows it (``change_employer``). With nothing
    running the new one is recorded on its own and points back at this follow-up's placement.
    Without details, a placement already running since then is the one linked."""
    from . import services as placements  # the module that re-exports this one

    if new_job is None:
        if running is None or running.pk == f.placement_id:
            raise FollowUpError("new_job", "Give the details of the new work.", "required")
        if (running.pathway == Placement.SELF) != (outcome == FollowUp.SELF_EMPLOYED):
            raise FollowUpError(
                "outcome", "The work already recorded does not match this outcome.", "mismatch"
            )
        return running
    unknown = set(new_job) - NEW_JOB_FIELDS
    if unknown:
        raise FollowUpError("new_job", f"Unknown field: {sorted(unknown)[0]}.", "unknown_field")
    job = dict(new_job)
    pathway = job.pop("pathway", "") or Placement.WAGE
    if outcome == FollowUp.SELF_EMPLOYED:
        pathway = Placement.SELF
    elif pathway == Placement.SELF:
        raise FollowUpError(
            "new_job", "Self-employment is its own outcome: choose “Now self-employed”.",
            "self_employment",
        )  # fmt: skip
    start = job.pop("start_date", None)
    if start is None:
        raise FollowUpError("new_job", "Give the date the new work started.", "required")
    if start > timezone.localdate():
        raise FollowUpError("new_job", "The new work cannot start in the future.", "future")
    try:
        if running is not None:
            if left_on is None:
                raise FollowUpError("left_on", "Give the date they left.", "required")
            return placements.change_employer(
                actor=actor, placement_id=running.pk, end_date=left_on, start_date=start,
                pathway=pathway, **job,
            )  # fmt: skip
        return placements.record_manual(
            actor=actor, enrollment_id=f.placement.enrollment_id, pathway=pathway,
            start_date=start, previous_placement_id=f.placement_id, **job,
        )  # fmt: skip
    except PlacementError as e:
        raise _as_followup_error(e, "new_job") from None


@transaction.atomic
def complete(
    *, actor, followup_id, evidence_source, still_employed=None, outcome="", note="",
    leaving_reason_id=None, left_on=None, observations="", new_job=None,
) -> FollowUp:  # fmt: skip
    """Record what the check-in found (FR-25; outcomes NEW-034, B25) and how we know.

    The outcome drives the youth's placements in the same transaction, so the follow-up and the
    placement history cannot disagree:

    - still with the same employer: this placement must still be running;
    - working for another employer, or now self-employed: the new work is recorded (or the one
      already recorded is linked) and the earlier one ended;
    - no longer working: a reason and the date they left are needed, and the running placement is
      ended with that reason.

    A call with only ``still_employed`` (the form before NEW-034) records the answer as before,
    with no change to the placements: True reads as the same employer, False as no longer working.
    """
    f = _locked_open(followup_id)
    legacy = not outcome
    if legacy:
        if still_employed is None:
            raise FollowUpError("outcome", "Say what the youth is doing now.", "required")
        outcome = FollowUp.SAME_EMPLOYER if still_employed else FollowUp.LEFT_EMPLOYMENT
    if outcome not in OUTCOMES:
        raise FollowUpError("outcome", "Choose one of the outcomes.", "unknown_outcome")
    if evidence_source not in SOURCES:
        raise FollowUpError("evidence_source", "Say how you know.", "evidence_required")
    today = timezone.localdate()
    note = _text("note", note, label="the note", limit=2000)
    observations = _text("observations", observations, label="the observations", limit=2000)
    if left_on is not None:
        if left_on > today:
            raise FollowUpError("left_on", "The date they left cannot be in the future.", "future")
        if f.placement.start_date and left_on < f.placement.start_date:
            raise FollowUpError(
                "left_on", "The date they left is before the placement started.", "before_start"
            )
    reason = None
    if leaving_reason_id:
        reason = configuration.outcome_item("leaving-reasons", leaving_reason_id)
        if reason is None:
            raise FollowUpError(
                "leaving_reason_id", "Choose a reason from the list.", "unknown_reason"
            )
    before = _snapshot(f)
    new_placement = None
    if not legacy:
        from . import services as placements

        running = placements.running_for_youth(f.placement.enrollment_id, lock=True)
        if outcome == FollowUp.SAME_EMPLOYER:
            if running is None or running.pk != f.placement_id:
                raise FollowUpError(
                    "outcome", "This placement is no longer running: choose another outcome.",
                    "not_running",
                )  # fmt: skip
            if reason or left_on:
                raise FollowUpError(
                    "leaving_reason_id", "They are still there: leave the reason and date out.",
                    "not_left",
                )  # fmt: skip
        elif outcome == FollowUp.LEFT_EMPLOYMENT:
            if reason is None:
                raise FollowUpError(
                    "leaving_reason_id", "Say why they are no longer working.", "required"
                )
            if left_on is None:
                raise FollowUpError("left_on", "Give the date they left.", "required")
            if reason["needs_note"] and not (note or observations):
                raise FollowUpError(
                    "observations", f"Explain “{reason['name']}” in the observations.",
                    "required",
                )  # fmt: skip
            if running is not None:
                try:
                    placements.end_episode(
                        actor=actor, placement_id=running.pk, end_date=left_on,
                        exit_reason=reason["name"],
                    )  # fmt: skip
                except PlacementError as e:
                    raise _as_followup_error(e, "left_on") from None
        else:
            new_placement = _new_work(
                f, actor=actor, outcome=outcome, running=running, left_on=left_on,
                new_job=new_job,
            )  # fmt: skip
    f.outcome = "" if legacy else outcome
    f.still_employed = outcome in FollowUp.EMPLOYED_OUTCOMES
    f.evidence_source, f.response_note, f.observations = evidence_source, note, observations
    f.leaving_reason_id = reason["id"] if reason else None
    f.left_on, f.new_placement = left_on, new_placement
    _close(f, actor=actor, status=FollowUp.DONE)
    f.save()
    audit.record(
        actor=actor, action="followup.completed", object_type="followup", object_id=f.pk,
        before=before, after=_snapshot(f),
    )  # fmt: skip
    return f


@transaction.atomic
def mark_unreachable(*, actor, followup_id, note="") -> FollowUp:
    """Give up on a follow-up after real attempts. At least one attempt must be on record."""
    f = _locked_open(followup_id)
    if not f.attempts.exists():
        raise FollowUpError(
            "status", "Log at least one attempt before closing this as unreachable.",
            "no_attempts",
        )  # fmt: skip
    before = _snapshot(f)
    f.response_note = _text("note", note, label="the note", limit=2000)
    _close(f, actor=actor, status=FollowUp.UNREACHABLE)
    f.save()
    audit.record(
        actor=actor, action="followup.unreachable", object_type="followup", object_id=f.pk,
        before=before, after=_snapshot(f),
    )  # fmt: skip
    return f


@transaction.atomic
def cancel(*, actor, followup_id, reason) -> FollowUp:
    """Stop a follow-up that no longer applies. A reason is required."""
    f = _locked_open(followup_id)
    reason = _text("reason", reason, label="why it is being cancelled", limit=500, required=True)
    before = _snapshot(f)
    f.response_note = reason
    _close(f, actor=actor, status=FollowUp.CANCELLED)
    f.save()
    audit.record(
        actor=actor, action="followup.cancelled", object_type="followup", object_id=f.pk,
        before=before, after=_snapshot(f), reason=reason,
    )  # fmt: skip
    return f


@transaction.atomic
def assign(*, actor, followup_id, owner_id, note="") -> FollowUp:
    """Hand a follow-up to another officer (caseload.reassign)."""
    owner = get_user_model().objects.filter(pk=owner_id, is_active=True).first()
    if owner is None or not has_permission(owner, WORKER_PERMISSION):
        raise FollowUpError("owner_id", "Choose an active officer who works cases.", "bad_user")
    f = _locked_open(followup_id)
    if f.assigned_to_id == owner.pk:
        return f
    before = _snapshot(f)
    f.assigned_to = owner
    f.save()
    audit.record(
        actor=actor, action="followup.assigned", object_type="followup", object_id=f.pk,
        before=before, after=_snapshot(f), reason=(note or "").strip()[:500],
    )  # fmt: skip
    return f


def history(followup: FollowUp) -> list[dict]:
    return audit.history("followup", followup.pk)
