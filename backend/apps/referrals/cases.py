"""Support interventions for case management (T-064, FR-21/FR-22). Re-exported by
``apps.referrals.services``; other modules call them as ``referrals.<name>``.

Every change is audited in the same transaction. An intervention is never deleted: stop one by
cancelling it. A youth outside the caller's scope is reported as not found."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.api.access import has_permission
from apps.audit import services as audit
from apps.participants import services as participants

from .models import Intervention, Referral
from .services import EDIT, RuleViolation, visible

NEEDS = dict(Intervention.NEEDS)
SOURCES = dict(Intervention.SOURCES)
DUE_SOON_DAYS = 7
# The referral stages that are waiting on staff to do something (a draft is not yet sent).
REFERRAL_WAITING = [Referral.DRAFT, Referral.SUBMITTED, Referral.UNDER_REVIEW, Referral.INTERVIEW]


def visible_interventions(user):
    """Interventions whose youth is inside the user's scope."""
    return Intervention.objects.filter(participant_id__in=participants.visible_ids(user))


def is_overdue(i: Intervention, today: date) -> bool:
    return i.status in Intervention.LIVE and i.due_date is not None and i.due_date < today


def next_statuses(i: Intervention) -> list[str]:
    order = [s for s, _ in Intervention.STATUSES]
    return sorted(Intervention.TRANSITIONS[i.status], key=order.index)


def _snapshot(i: Intervention) -> dict:
    return {
        "status": i.status,
        "need": i.need,
        "title": i.title,
        "owner": i.owner_id,
        "due_date": i.due_date.isoformat() if i.due_date else None,
        "verification_source": i.verification_source,
    }


def _worker(user_id):
    """An active user who is allowed to work cases (referrals.edit), or a violation."""
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if user is None or not has_permission(user, EDIT):
        raise RuleViolation("owner_id", "Choose an active officer who works cases.", "bad_user")
    return user


def _check_text(field, value, *, label, limit, required=False):
    value = (value or "").strip()
    if required and not value:
        raise RuleViolation(field, f"Say {label}.", "required")
    if len(value) > limit:
        raise RuleViolation(field, f"Keep {label} under {limit} characters.", "too_long")
    return value


def _check_due(due_date, today):
    if due_date is not None and due_date < today:
        raise RuleViolation("due_date", "The due date cannot be in the past.", "past_due")


@transaction.atomic
def create_intervention(
    *, actor, participant_id, need, title, detail="", owner_id=None, due_date=None,
    follow_up_of_id=None,
):  # fmt: skip
    """Record a support need and the action to meet it (FR-21). The owner is the actor unless
    another officer is named. A follow-up names the intervention it follows."""
    parent = None
    if follow_up_of_id:
        parent = visible_interventions(actor).filter(pk=follow_up_of_id).first()
        if parent is None:
            raise RuleViolation("follow_up_of_id", "Intervention not found.", "unknown")
        participant_id = parent.participant_id
    if not participants.is_visible(actor, participant_id):
        raise RuleViolation("participant_id", "Youth not found.", "unknown_participant")
    if need not in NEEDS:
        raise RuleViolation("need", "Choose the kind of support needed.", "unknown_need")
    title = _check_text("title", title, label="what will be done", limit=200, required=True)
    detail = _check_text("detail", detail, label="the details", limit=4000)
    _check_due(due_date, timezone.localdate())
    owner = _worker(owner_id) if owner_id else actor
    i = Intervention.objects.create(
        participant_id=participant_id, need=need, title=title, detail=detail, owner=owner,
        due_date=due_date, follow_up_of=parent, created_by=actor,
    )  # fmt: skip
    audit.record(
        actor=actor, action="intervention.created", object_type="intervention",
        object_id=i.pk, after={**_snapshot(i), "participant": str(participant_id),
                               "follow_up_of": str(parent.pk) if parent else None},
    )  # fmt: skip
    return i


@transaction.atomic
def update_intervention(*, actor, intervention, **changes):
    """Change the wording, need or due date while the intervention is still live."""
    i = Intervention.objects.select_for_update().get(pk=intervention.pk)
    if i.status not in Intervention.LIVE:
        raise RuleViolation("status", "A closed or cancelled intervention cannot be edited.",
                            "not_live")  # fmt: skip
    before = _snapshot(i)
    if "need" in changes:
        if changes["need"] not in NEEDS:
            raise RuleViolation("need", "Choose the kind of support needed.", "unknown_need")
        i.need = changes["need"]
    if "title" in changes:
        i.title = _check_text("title", changes["title"], label="what will be done", limit=200,
                              required=True)  # fmt: skip
    if "detail" in changes:
        i.detail = _check_text("detail", changes["detail"], label="the details", limit=4000)
    if "due_date" in changes:
        if changes["due_date"] != i.due_date:  # an already-overdue date may stay as it is
            _check_due(changes["due_date"], timezone.localdate())
        i.due_date = changes["due_date"]
    i.save()
    audit.record(
        actor=actor, action="intervention.updated", object_type="intervention",
        object_id=i.pk, before=before, after=_snapshot(i),
    )  # fmt: skip
    return i


@transaction.atomic
def move_intervention(*, actor, intervention, to, verification_source="", note=""):
    """Move along open → in progress → awaiting verification → closed (or cancel). Closing needs
    the verification source; cancelling needs a reason in the note."""
    i = Intervention.objects.select_for_update().get(pk=intervention.pk)
    if to not in Intervention.TRANSITIONS[i.status]:
        raise RuleViolation("to", f"Cannot go from {i.status} to {to}.", "bad_transition")
    note = _check_text("note", note, label="the note", limit=2000)
    before = _snapshot(i)
    if to == Intervention.CLOSED:
        if verification_source not in SOURCES:
            raise RuleViolation(
                "verification_source", "Say how you know the support happened.",
                "verification_required",
            )  # fmt: skip
        i.verification_source = verification_source
    if to == Intervention.CANCELLED and not note:
        raise RuleViolation("note", "Say why this is being cancelled.", "note_required")
    if to in (Intervention.CLOSED, Intervention.CANCELLED):
        i.outcome_note, i.closed_at = note, timezone.now()
    i.status = to
    i.save()
    audit.record(
        actor=actor, action="intervention.status_changed", object_type="intervention",
        object_id=i.pk, before=before, after=_snapshot(i), reason=note,
    )  # fmt: skip
    return i


@transaction.atomic
def assign_intervention(*, actor, intervention, owner_id, note=""):
    """Hand an intervention to another officer (caseload.reassign)."""
    owner = _worker(owner_id)
    i = Intervention.objects.select_for_update().get(pk=intervention.pk)
    if i.status not in Intervention.LIVE:
        raise RuleViolation("status", "A closed or cancelled intervention cannot be reassigned.",
                            "not_live")  # fmt: skip
    if i.owner_id == owner.pk:
        return i
    before = _snapshot(i)
    i.owner = owner
    i.save()
    audit.record(
        actor=actor, action="intervention.assigned", object_type="intervention",
        object_id=i.pk, before=before, after=_snapshot(i), reason=note,
    )  # fmt: skip
    return i


def counts_for(user, *, mine: bool, today: date) -> dict:
    """Headline numbers for the work queue: live, overdue, due soon, awaiting verification."""
    qs = visible_interventions(user).filter(status__in=Intervention.LIVE)
    if mine:
        qs = qs.filter(owner=user)
    return {
        "live": qs.count(),
        "overdue": qs.filter(due_date__lt=today).count(),
        "due_soon": qs.filter(
            due_date__gte=today, due_date__lte=today + timedelta(days=DUE_SOON_DAYS)
        ).count(),
        "awaiting_verification": qs.filter(status=Intervention.AWAITING).count(),
    }


def queue_interventions(user, *, mine: bool, today: date, limit: int = 50) -> list[dict]:
    """Live interventions for the work queue: overdue first, then by due date (none last)."""
    qs = visible_interventions(user).filter(status__in=Intervention.LIVE)
    if mine:
        qs = qs.filter(owner=user)
    rows = list(qs.select_related("participant", "owner"))
    rows.sort(
        key=lambda i: (
            not is_overdue(i, today),
            i.due_date is None,
            i.due_date or today,
            i.created_at,
        )
    )
    return [
        {
            "id": str(i.pk),
            "participant_id": str(i.participant_id),
            "participant": i.participant.full_name_source,
            "need_label": NEEDS[i.need],
            "title": i.title,
            "status": i.status,
            "status_label": dict(Intervention.STATUSES)[i.status],
            "owner": (i.owner.get_full_name() or i.owner.get_username()) if i.owner_id else "",
            "due_date": i.due_date.isoformat() if i.due_date else None,
            "overdue": is_overdue(i, today),
        }
        for i in rows[:limit]
    ]


def queue_referrals(user, *, mine: bool, now, limit: int = 50) -> tuple[int, list[dict]]:
    """Referrals waiting on staff, longest-waiting first, with the count before the limit."""
    qs = visible(user).filter(stage__in=REFERRAL_WAITING)
    if mine:
        qs = qs.filter(assigned_to=user)
    total = qs.count()
    rows = qs.select_related("participant", "opportunity__employer", "assigned_to")
    return total, [
        {
            "id": str(r.pk),
            "participant_id": str(r.participant_id),
            "participant": r.participant.full_name_source,
            "opportunity": r.opportunity.title,
            "employer": r.opportunity.employer.name,
            "stage": r.stage,
            "stage_label": dict(Referral.STAGES)[r.stage],
            "assigned_to": (r.assigned_to.get_full_name() or r.assigned_to.get_username())
            if r.assigned_to_id
            else "",
            "days_waiting": (now - r.updated_at).days,
        }
        for r in rows.order_by("updated_at")[:limit]
    ]
