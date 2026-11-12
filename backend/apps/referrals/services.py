"""Public interface of apps.referrals (T-046). Other modules import only this module.

Every change writes a stage event (the referral's own history) and an audit event, in the same
transaction as the change, so all three commit or none does."""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from apps.api.access import has_permission
from apps.audit import services as audit
from apps.configuration import services as configuration
from apps.employers import services as employers
from apps.participants import services as participants

from .models import Referral, StageEvent

EDIT, APPROVE = "referrals.edit", "referrals.approve"


class RuleViolation(Exception):
    def __init__(self, field, message, code):
        super().__init__(message)
        self.field, self.message, self.code = field, message, code


def visible(user):
    """Referrals the user may see: those whose youth is inside the user's scope."""
    return Referral.objects.filter(participant_id__in=participants.visible_ids(user))


def next_stages(referral) -> list[str]:
    order = [s for s, _ in Referral.STAGES]
    return sorted(Referral.TRANSITIONS[referral.stage], key=order.index)


def _label(actor):
    return actor.get_username()[:150] if actor is not None else "system"


def _check_reason(to, reason_id, note):
    """FR-18: an unsuccessful outcome needs an active reason code that applies to it."""
    if to not in Referral.UNSUCCESSFUL:
        return None
    if not reason_id:
        raise RuleViolation("reason_id", "Choose a reason for this outcome.", "reason_required")
    reason = configuration.referral_reason(reason_id)
    if reason is None or not reason["active"]:
        raise RuleViolation("reason_id", "Unknown or inactive reason.", "unknown_reason")
    if reason["applies_to"] not in (to, "any"):
        raise RuleViolation(
            "reason_id", "That reason does not apply to this outcome.", "reason_mismatch"
        )
    if reason["needs_note"] and not note.strip():
        raise RuleViolation(
            "note", "This reason needs a note saying what happened.", "note_required"
        )
    return reason["id"]


def referred_participant_ids(opportunity_id) -> set:
    """Youth who already have an open or placed referral to this opportunity."""
    return set(
        Referral.objects.filter(
            opportunity_id=opportunity_id, stage__in=Referral.ACTIVE | {Referral.PLACED}
        ).values_list("participant_id", flat=True)
    )


def _check_no_other_active(referral):
    clash = Referral.objects.filter(
        participant_id=referral.participant_id,
        opportunity_id=referral.opportunity_id,
        stage__in=Referral.ACTIVE,
    ).exclude(pk=referral.pk)
    if clash.exists():
        raise RuleViolation(
            "opportunity_id",
            "This youth already has an open referral to this opportunity.",
            "duplicate",
        )


def _event(referral, *, actor, kind, from_stage, to, reason_id=None, note="", corrects=None):
    return StageEvent.objects.create(
        referral=referral, kind=kind, from_stage=from_stage, to_stage=to, reason_id=reason_id,
        note=note, corrects=corrects, actor=actor, actor_label=_label(actor), at=timezone.now(),
    )  # fmt: skip


def _snapshot(r):
    return {
        "stage": r.stage,
        "reason": str(r.reason_id) if r.reason_id else None,
        "assigned_to": r.assigned_to_id,
    }


def _apply_stage(referral, to, reason_id, note, now):
    referral.stage = to
    if to in Referral.UNSUCCESSFUL:
        referral.reason_id, referral.reason_note = reason_id, note
    elif to != Referral.CLOSED:  # closing keeps the outcome's reason on the record
        referral.reason_id, referral.reason_note = None, ""
    if to == Referral.SUBMITTED and referral.referred_at is None:
        referral.referred_at = now
    referral.closed_at = now if to == Referral.CLOSED else None


@transaction.atomic
def create_referral(*, actor, participant_id, opportunity_id, note="", submit=True):
    """A staff referral (FR-16). ``submit`` sends it straight on; otherwise it stays a draft."""
    if not participants.is_visible(actor, participant_id):
        raise RuleViolation("participant_id", "Youth not found.", "unknown_participant")
    if not employers.accepts_referrals(opportunity_id):
        raise RuleViolation(
            "opportunity_id", "This opportunity is not open for referrals.", "opportunity_closed"
        )
    now = timezone.now()
    referral = Referral(
        participant_id=participant_id, opportunity_id=opportunity_id, origin=Referral.OFFICER,
        assigned_to=actor, created_by=actor,
    )  # fmt: skip
    _check_no_other_active(referral)
    try:
        with transaction.atomic():
            referral.save()
    except IntegrityError as exc:  # two people referring at the same moment
        raise RuleViolation(
            "opportunity_id",
            "This youth already has an open referral to this opportunity.",
            "duplicate",
        ) from exc
    _event(referral, actor=actor, kind=StageEvent.TRANSITION, from_stage="", to=Referral.DRAFT,
           note=note)  # fmt: skip
    if submit:
        _apply_stage(referral, Referral.SUBMITTED, None, "", now)
        referral.save()
        _event(referral, actor=actor, kind=StageEvent.TRANSITION, from_stage=Referral.DRAFT,
               to=Referral.SUBMITTED)  # fmt: skip
    audit.record(
        actor=actor, action="referral.created", object_type="referral", object_id=referral.pk,
        after={"participant": str(participant_id), "opportunity": str(opportunity_id),
               "origin": referral.origin, "stage": referral.stage},
    )  # fmt: skip
    return referral


@transaction.atomic
def transition(*, actor, referral, to, reason_id=None, note=""):
    """Move a referral one step along the stage model (FR-16, FR-17, FR-18)."""
    referral = Referral.objects.select_for_update().get(pk=referral.pk)
    if to not in Referral.TRANSITIONS[referral.stage]:
        raise RuleViolation("to", f"Cannot go from {referral.stage} to {to}.", "bad_transition")
    reason_id = _check_reason(to, reason_id, note)
    if to == Referral.CLOSED and referral.stage in Referral.UNSUCCESSFUL and not referral.reason_id:
        raise RuleViolation(
            "reason_id", "An unsuccessful referral needs a reason before it closes.",
            "reason_required",
        )  # fmt: skip
    if to == Referral.SUBMITTED and not employers.accepts_referrals(referral.opportunity_id):
        raise RuleViolation(
            "to", "This opportunity is no longer open for referrals.", "opportunity_closed"
        )
    before, from_stage = _snapshot(referral), referral.stage
    _apply_stage(referral, to, reason_id, note, timezone.now())
    referral.save()
    _event(referral, actor=actor, kind=StageEvent.TRANSITION, from_stage=from_stage, to=to,
           reason_id=reason_id, note=note)  # fmt: skip
    audit.record(
        actor=actor, action="referral.stage_changed", object_type="referral",
        object_id=referral.pk, before=before, after=_snapshot(referral), reason=note,
    )  # fmt: skip
    return referral


@transaction.atomic
def set_interview(*, actor, referral, at, place="", note=""):
    """Record when and where the interview is, for the learner to see. Only while the referral
    is at the interview stage, so the details never describe a stage it is not in."""
    referral = Referral.objects.select_for_update().get(pk=referral.pk)
    if referral.stage != Referral.INTERVIEW:
        raise RuleViolation(
            "stage", "Move the referral to Interview before adding interview details.",
            "not_interview",
        )  # fmt: skip
    before = {"interview_at": referral.interview_at.isoformat() if referral.interview_at else None}
    referral.interview_at, referral.interview_place = at, place
    referral.interview_note, referral.interview_set_at = note, timezone.now()
    referral.save(
        update_fields=[
            "interview_at", "interview_place", "interview_note", "interview_set_at", "updated_at"
        ]
    )  # fmt: skip
    audit.record(
        actor=actor, action="referral.interview_set", object_type="referral",
        object_id=referral.pk, before=before, after={"interview_at": at.isoformat()},
    )  # fmt: skip
    return referral


@transaction.atomic
def correct(*, actor, referral, to, note, reason_id=None):
    """Put a referral back to the stage it should be in (FR-19), e.g. reopen a closed one.

    Nothing is overwritten: a new correction event points at the event it corrects, so the
    history shows both. The person must say why."""
    referral = Referral.objects.select_for_update().get(pk=referral.pk)
    if not note.strip():
        raise RuleViolation("note", "Say why this correction is needed.", "note_required")
    if to == referral.stage:
        raise RuleViolation("to", "The referral is already at that stage.", "same_stage")
    if to not in Referral.TRANSITIONS or to == Referral.CLOSED:
        raise RuleViolation("to", "Close a referral with a normal move.", "bad_correction")
    reason_id = _check_reason(to, reason_id, note)
    if to in Referral.ACTIVE:
        _check_no_other_active(referral)
    last = referral.events.order_by("-at", "-id").first()
    before, from_stage = _snapshot(referral), referral.stage
    _apply_stage(referral, to, reason_id, note, timezone.now())
    referral.save()
    _event(referral, actor=actor, kind=StageEvent.CORRECTION, from_stage=from_stage, to=to,
           reason_id=reason_id, note=note, corrects=last)  # fmt: skip
    audit.record(
        actor=actor, action="referral.corrected", object_type="referral",
        object_id=referral.pk, before=before, after=_snapshot(referral), reason=note,
    )  # fmt: skip
    return referral


def assignees():
    """Active staff who can work referrals, for the assign drop-down."""
    users = get_user_model().objects.filter(is_active=True).order_by("username")
    return [
        {"id": u.pk, "name": u.get_full_name() or u.get_username()}
        for u in users
        if has_permission(u, EDIT)
    ]


@transaction.atomic
def assign(*, actor, referral, user_id, note=""):
    """Hand a referral to another officer (caseload.reassign)."""
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if user is None or not has_permission(user, EDIT):
        raise RuleViolation("user_id", "Choose an active officer who works referrals.", "bad_user")
    if referral.assigned_to_id == user.pk:
        return referral
    before = _snapshot(referral)
    referral.assigned_to = user
    referral.save(update_fields=["assigned_to", "updated_at"])
    audit.record(
        actor=actor, action="referral.assigned", object_type="referral", object_id=referral.pk,
        before=before, after=_snapshot(referral), reason=note,
    )  # fmt: skip
    return referral


def stage_history(referral) -> list[dict]:
    """Oldest-first stage events, corrections included (FR-17, FR-19)."""
    return [
        {
            "id": e.pk,
            "kind": e.kind,
            "from": e.from_stage,
            "to": e.to_stage,
            "reason": e.reason.name if e.reason_id else "",
            "note": e.note,
            "corrects": e.corrects_id,
            "actor": e.actor_label,
            "at": e.at.isoformat(),
        }
        for e in referral.events.select_related("reason")
    ]


def counts_by_stage(user) -> dict[str, int]:
    rows = visible(user).values("stage").annotate(n=Count("pk"))
    return {r["stage"]: r["n"] for r in rows}


def counts_by_opportunity(user) -> dict[str, dict[str, int]]:
    """Per opportunity: referred, in progress, placed, unsuccessful (scope applied)."""
    rows = visible(user).values("opportunity_id", "stage").annotate(n=Count("pk"))
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        o = out.setdefault(
            str(r["opportunity_id"]),
            {"referred": 0, "in_progress": 0, "placed": 0, "unsuccessful": 0},
        )
        o["referred"] += r["n"]
        if r["stage"] in Referral.ACTIVE:
            o["in_progress"] += r["n"]
        elif r["stage"] == Referral.PLACED:
            o["placed"] += r["n"]
        elif r["stage"] in Referral.UNSUCCESSFUL:
            o["unsuccessful"] += r["n"]
    return out


# ---- the learner's own view (youth portal) ---------------------------------------------------
# A youth sees only their own submitted referrals, in plain words. Never exposed here: match
# scores, other youth, staff notes, reasons for a rejection, or who handled it.

LEARNER_STEPS = [
    (Referral.SUBMITTED, "Referred"),
    (Referral.UNDER_REVIEW, "Under review"),
    (Referral.INTERVIEW, "Interview"),
    (Referral.SELECTED, "Selected"),
    (Referral.PLACED, "Placed"),
]
_STEP_KEYS = [k for k, _ in LEARNER_STEPS]
_LEARNER_LABEL = {
    **dict(LEARNER_STEPS),
    Referral.REJECTED: "Not selected",
    Referral.NO_RESPONSE: "Not selected",
    Referral.WITHDRAWN: "Withdrawn",
}


def _learner_stage(referral, reached: set) -> str:
    """The stage as the learner sees it. A closed referral shows how it ended."""
    if referral.stage != Referral.CLOSED:
        return referral.stage
    for s in (Referral.PLACED, Referral.REJECTED, Referral.NO_RESPONSE, Referral.WITHDRAWN):
        if s in reached:
            return s
    return Referral.CLOSED


def _learner_interview(r):
    if r.interview_at is None:
        return None
    return {"at": r.interview_at.isoformat(), "place": r.interview_place, "note": r.interview_note}


def _learner_row(r, reached) -> dict:
    stage = _learner_stage(r, reached)
    o = r.opportunity
    return {
        "id": str(r.id),
        "opportunity": o.title,
        "employer": o.employer.name,
        "kind": o.kind,
        "location": o.location or (o.county.name if o.county_id else ""),
        "stage": stage,
        "stage_label": _LEARNER_LABEL.get(stage, "Closed"),
        "ended": stage not in Referral.ACTIVE and stage != Referral.PLACED,
        "referred_at": r.referred_at.date().isoformat() if r.referred_at else None,
        "updated_at": r.updated_at.date().isoformat(),
        "reached": [s for s in _STEP_KEYS if s in reached or s == stage],
        "interview": _learner_interview(r) if stage == Referral.INTERVIEW else None,
    }


def _learner_qs(participant_id):
    return (
        Referral.objects.filter(participant_id=participant_id)
        .exclude(stage=Referral.DRAFT)
        .select_related("opportunity__employer", "opportunity__county")
        .prefetch_related("events")
        .order_by("-referred_at", "-created_at")
    )


def learner_journey(participant_id) -> dict:
    """Counters, the journey steps and the learner's referrals, newest first."""
    rows = []
    for r in _learner_qs(participant_id):
        reached = {e.to_stage for e in r.events.all()}
        rows.append(_learner_row(r, reached))
    counts = {
        "referred": len(rows),
        "interview": sum(1 for x in rows if "interview" in x["reached"]),
        "selected": sum(1 for x in rows if "selected" in x["reached"]),
        "placed": sum(1 for x in rows if x["stage"] == Referral.PLACED),
    }
    return {
        "steps": [{"key": k, "label": label} for k, label in LEARNER_STEPS],
        "counts": counts,
        "latest": rows[0] if rows else None,
        "items": rows,
    }


def learner_referral(participant_id, referral_id) -> dict | None:
    """One of the learner's own referrals with its plain-language timeline, or None."""
    r = _learner_qs(participant_id).filter(pk=referral_id).first()
    if r is None:
        return None
    events = list(r.events.order_by("at", "id"))
    reached = {e.to_stage for e in events}
    o = r.opportunity
    timeline = [
        {
            "label": _LEARNER_LABEL.get(e.to_stage, "Closed"),
            "at": e.at.date().isoformat(),
        }
        for e in events
        if e.to_stage in _LEARNER_LABEL and e.kind == StageEvent.TRANSITION
    ]
    return {
        **_learner_row(r, reached),
        "description": o.description,
        "start_date": o.start_date.isoformat() if o.start_date else None,
        "closing_date": o.closing_date.isoformat() if o.closing_date else None,
        "timeline": timeline,
    }


def learner_notices(participant_id, since=None) -> dict:
    """Plain-language updates for the learner, newest first: each step reached and each time
    interview details were set or changed. ``unread`` counts those after ``since``."""
    items = []
    for r in _learner_qs(participant_id):
        title = r.opportunity.title
        for e in r.events.all():
            if e.kind == StageEvent.TRANSITION and e.to_stage in _LEARNER_LABEL:
                items.append(
                    {
                        "referral_id": str(r.id),
                        "text": f"{title}: {_LEARNER_LABEL[e.to_stage]}",
                        "at": e.at,
                    }
                )
        if r.interview_set_at and r.stage == Referral.INTERVIEW:
            items.append(
                {
                    "referral_id": str(r.id),
                    "text": f"{title}: interview details added or changed",
                    "at": r.interview_set_at,
                }
            )
    items.sort(key=lambda i: i["at"], reverse=True)
    unread = sum(1 for i in items if since is None or i["at"] > since)
    return {
        "unread": unread,
        "items": [{**i, "at": i["at"].isoformat()} for i in items[:30]],
    }


def learner_placed(participant_id) -> list[dict]:
    """Referrals that ended in a placement, as the learner sees them."""
    out = []
    for r in _learner_qs(participant_id):
        reached = {e.to_stage for e in r.events.all()}
        if _learner_stage(r, reached) == Referral.PLACED:
            o = r.opportunity
            placed_at = max(
                (e.at for e in r.events.all() if e.to_stage == Referral.PLACED), default=None
            )
            out.append(
                {
                    "id": str(r.id),
                    "employer": o.employer.name,
                    "designation": o.title,
                    "kind": o.kind,
                    "location": o.location or (o.county.name if o.county_id else ""),
                    "start_date": o.start_date.isoformat() if o.start_date else None,
                    "placed_on": placed_at.date().isoformat() if placed_at else None,
                }
            )
    return out


# ---- Facts for the intelligence modules (counts only; no judgement lives here) ----


def employer_counts(employer_id, since) -> dict:
    """What happened to referrals sent to one employer since ``since``: raw counts and the
    waiting times, nothing interpreted. Retention and feedback are not recorded yet."""
    sent = Referral.objects.filter(opportunity__employer_id=employer_id, referred_at__gte=since)
    ids = list(sent.values_list("pk", flat=True))
    first_reply = {}
    for ev in StageEvent.objects.filter(
        referral_id__in=ids, kind=StageEvent.TRANSITION, from_stage=Referral.SUBMITTED
    ).order_by("at", "id"):
        first_reply.setdefault(ev.referral_id, ev.at)
    referred_at = dict(sent.values_list("pk", "referred_at"))
    days = sorted((first_reply[i] - referred_at[i]).total_seconds() / 86400 for i in first_reply)
    reached = StageEvent.objects.filter(
        referral_id__in=ids, to_stage=Referral.INTERVIEW
    ).values("referral_id").distinct().count()  # fmt: skip
    placed = (
        StageEvent.objects.filter(referral_id__in=ids, to_stage=Referral.PLACED)
        .values("referral_id")
        .distinct()
        .count()
    )
    return {
        "sent": len(ids),
        "replied": len(first_reply),
        "reply_days_median": round(days[len(days) // 2], 1) if days else None,
        "interview": reached,
        "placed": placed,
    }


def support_facts(ids, *, since, stalled_before) -> dict:
    """Per-youth facts that the support-priority flags read (Module A): unsuccessful referrals
    since a date, open referrals untouched since a date, and who has ever been referred."""
    ids = list(ids)
    unsuccessful = dict(
        StageEvent.objects.filter(
            referral__participant_id__in=ids,
            to_stage__in=Referral.UNSUCCESSFUL,
            kind=StageEvent.TRANSITION,
            at__gte=since,
        )
        .values_list("referral__participant_id")
        .annotate(n=Count("referral_id", distinct=True))
    )
    stalled: dict = {}
    open_stages = Referral.ACTIVE - {Referral.DRAFT}
    for r in (
        Referral.objects.filter(
            participant_id__in=ids, stage__in=open_stages, updated_at__lte=stalled_before
        )
        .select_related("opportunity")
        .order_by("updated_at")
    ):
        stalled.setdefault(r.participant_id, (r.opportunity.title, r.updated_at))
    referred = set(
        Referral.objects.filter(participant_id__in=ids)
        .exclude(stage=Referral.DRAFT)
        .values_list("participant_id", flat=True)
    )
    return {"unsuccessful": unsuccessful, "stalled": stalled, "referred": referred}
