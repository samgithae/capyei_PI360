"""One company's own referrals, for the employer portal.

Every function takes the ``employer_id`` the portal resolved from the signed-in user's
membership and limits every query to referrals for that company's opportunities. A referral that
is not this company's is "missing", exactly as if it did not exist. Draft referrals (staff are
still preparing them) are never shown.

What a company sees is deliberately smaller than what staff see. Never returned: staff notes,
which staff member handled a referral, match scores and rule versions, the candidate's national
ID, date of birth or gender, other companies' referrals. The candidate's phone and email appear
only once the company has selected them.

``people`` is ``{user id: name}`` of the company's own users, supplied by the portal, so history
can say "Wanjiru (you)" for the company's own moves and "PI360 placement team" for staff moves
without this module knowing about company accounts.

Import ``services`` (which re-exports everything here), never this module directly.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncWeek
from django.utils import timezone

from apps.configuration import services as configuration
from apps.participants import services as participants

from . import services
from .models import Referral, StageEvent

STAFF_TEAM = "PI360 placement team"
# What a company may decide. Placing and closing stay with PI staff, who confirm the hire.
EMPLOYER_MOVES = (
    Referral.UNDER_REVIEW,
    Referral.INTERVIEW,
    Referral.SELECTED,
    Referral.REJECTED,
)
STAGE_NAMES = dict(Referral.STAGES)
# Employer wording for the same stages.
EMPLOYER_LABELS = {
    Referral.SUBMITTED: "New",
    Referral.UNDER_REVIEW: "Under review",
    Referral.INTERVIEW: "Interview",
    Referral.SELECTED: "Selected",
    Referral.REJECTED: "Not selected",
    Referral.NO_RESPONSE: "Not selected",
    Referral.WITHDRAWN: "Withdrawn",
    Referral.PLACED: "Placed",
    Referral.CLOSED: "Closed",
}


class Missing(LookupError):
    """The referral does not exist, or belongs to another company."""


def _qs(employer_id):
    return (
        Referral.objects.filter(opportunity__employer_id=employer_id)
        .exclude(stage=Referral.DRAFT)
        .select_related("participant", "opportunity")
    )


def _referral(employer_id, pk):
    try:
        r = _qs(employer_id).filter(pk=pk).first()
    except (ValueError, TypeError):
        r = None
    if r is None:
        raise Missing
    return r


def pair_of(employer_id, pk) -> dict:
    """The youth and opportunity ids behind one of this company's referrals, for the checks that
    explain the match (the caller that needs them lives outside this module)."""
    r = _referral(employer_id, pk)
    return {"participant_id": r.participant_id, "opportunity_id": r.opportunity_id}


def _contact_visible(r) -> bool:
    """Phone and email are shown from the moment the company selects the candidate, and stay
    through placement. They are not shown for a withdrawn or unsuccessful referral."""
    if r.stage in (Referral.SELECTED, Referral.PLACED):
        return True
    return r.stage == Referral.CLOSED and r.events.filter(to_stage=Referral.PLACED).exists()


def _summary(r) -> dict:
    return {
        "id": str(r.pk),
        "candidate": r.participant.full_name_source,
        "opportunity_id": str(r.opportunity_id),
        "opportunity": r.opportunity.title,
        "stage": r.stage,
        "stage_label": EMPLOYER_LABELS.get(r.stage, STAGE_NAMES[r.stage]),
        "referred_at": r.referred_at.isoformat() if r.referred_at else None,
        "interview_at": r.interview_at.isoformat() if r.interview_at else None,
        "updated_at": r.updated_at.isoformat(),
        # Waiting for the company to look at it.
        "needs_action": r.stage in (Referral.SUBMITTED, Referral.UNDER_REVIEW, Referral.INTERVIEW),
    }


WAITING_DAYS = 3  # a new referral unanswered this long is "waiting"
REPLY_WINDOW_DAYS = 365
VIEWS = ("new", "review", "interviews", "selected", "placed_ytd", "replied", "waiting")


def _view(qs, view, now):
    """Named lists the dashboard counts and links to. The figure and the list behind it use this
    one function, so they cannot disagree."""
    today = now.date()
    if view == "new":
        return qs.filter(stage=Referral.SUBMITTED)
    if view == "review":
        return qs.filter(stage=Referral.UNDER_REVIEW)
    if view == "interviews":
        return qs.filter(stage=Referral.INTERVIEW, interview_at__date__gte=today)
    if view == "selected":
        return qs.filter(stage=Referral.SELECTED)
    if view == "placed_ytd":
        return qs.filter(
            events__to_stage=Referral.PLACED,
            events__at__gte=now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
        ).distinct()
    if view == "replied":
        return qs.filter(
            referred_at__gte=now - timedelta(days=REPLY_WINDOW_DAYS),
            events__kind=StageEvent.TRANSITION,
            events__from_stage=Referral.SUBMITTED,
        ).distinct()
    if view == "waiting":
        return qs.filter(
            stage=Referral.SUBMITTED, referred_at__lte=now - timedelta(days=WAITING_DAYS)
        )
    return qs


def own_referrals(
    employer_id, *, stage="", q="", opportunity="", view="", offset=0, size=25, now=None
) -> dict:
    base = _qs(employer_id)
    counts = {
        row["stage"]: row["n"] for row in base.order_by().values("stage").annotate(n=Count("pk"))
    }
    qs = base
    if stage in EMPLOYER_LABELS:
        qs = qs.filter(stage=stage)
    if view in VIEWS:
        qs = _view(qs, view, now or timezone.now())
    if opportunity:
        try:
            qs = qs.filter(opportunity_id=opportunity)
        except (ValueError, TypeError, ValidationError):
            qs = qs.none()
    if q.strip():
        term = q.strip()
        qs = qs.filter(
            Q(participant__full_name_source__icontains=term) | Q(opportunity__title__icontains=term)
        )
    qs = qs.order_by("-referred_at", "-created_at")
    return {
        "total": qs.count(),
        "page_size": size,
        "counts": counts,
        "results": [_summary(r) for r in qs[offset : offset + size]],
    }


FUNNEL = (
    Referral.SUBMITTED,
    Referral.UNDER_REVIEW,
    Referral.INTERVIEW,
    Referral.SELECTED,
    Referral.PLACED,
    Referral.REJECTED,
)


def own_dashboard(employer_id, *, people, now=None) -> dict:
    """Figures, funnel, weekly trend, per-opportunity counts and recent moves for one company.
    Every figure comes from the same ``_view`` the list uses."""
    now = now or timezone.now()
    base = _qs(employer_id)
    figures = {v: _view(base, v, now).count() for v in VIEWS}
    since = now - timedelta(days=REPLY_WINDOW_DAYS)
    median = services.employer_counts(employer_id, since)["reply_days_median"]
    by_stage = {
        row["stage"]: row["n"] for row in base.order_by().values("stage").annotate(n=Count("pk"))
    }
    funnel = [
        {"stage": st, "label": EMPLOYER_LABELS[st], "count": by_stage.get(st, 0)} for st in FUNNEL
    ]
    weeks = {
        row["w"].date(): row["n"]
        for row in base.filter(referred_at__gte=now - timedelta(weeks=12))
        .annotate(w=TruncWeek("referred_at"))
        .order_by()
        .values("w")
        .annotate(n=Count("pk"))
    }
    monday = (now - timedelta(days=now.weekday())).date()
    trend = [
        {"week": (w := monday - timedelta(weeks=i)).isoformat(), "count": weeks.get(w, 0)}
        for i in range(11, -1, -1)
    ]
    per_opportunity = [
        {
            "opportunity_id": str(row["opportunity_id"]),
            "opportunity": row["opportunity__title"],
            "total": row["n"],
            "new": row["new"],
        }
        for row in base.order_by()
        .values("opportunity_id", "opportunity__title")
        .annotate(n=Count("pk"), new=Count("pk", filter=Q(stage=Referral.SUBMITTED)))
        .order_by("-new", "-n", "opportunity__title")[:10]
    ]
    recent = []
    events = (
        StageEvent.objects.filter(
            referral__opportunity__employer_id=employer_id, kind=StageEvent.TRANSITION
        )
        .exclude(from_stage="")
        .exclude(referral__stage=Referral.DRAFT)
        .select_related("referral__participant", "referral__opportunity")
        .order_by("-at", "-id")[:10]
    )
    for e in events:
        own = e.actor_id in people
        recent.append(
            {
                "at": e.at.isoformat(),
                "referral_id": str(e.referral_id),
                "candidate": e.referral.participant.full_name_source,
                "opportunity": e.referral.opportunity.title,
                "to": e.to_stage,
                "label": EMPLOYER_LABELS.get(e.to_stage, STAGE_NAMES.get(e.to_stage, e.to_stage)),
                "by": people[e.actor_id] if own else STAFF_TEAM,
                "own": own,
            }
        )
    fresh = (
        base.filter(referred_at__gte=now - timedelta(days=7))
        .order_by()
        .values("opportunity_id", "opportunity__title")
        .annotate(n=Count("pk"), last=Max("referred_at"))
        .order_by("-last")[:5]
    )
    arrivals = [
        {
            "at": row["last"].isoformat(),
            "opportunity_id": str(row["opportunity_id"]),
            "opportunity": row["opportunity__title"],
            "count": row["n"],
        }
        for row in fresh
    ]
    return {
        "figures": figures,
        "reply_days_median": median,
        "reply_window_days": REPLY_WINDOW_DAYS,
        "waiting_days": WAITING_DAYS,
        "funnel": funnel,
        "trend": trend,
        "per_opportunity": per_opportunity,
        "recent_moves": recent,
        "new_arrivals": arrivals,
    }


def _history(r, people) -> list[dict]:
    """The company's own moves with their notes, and staff moves as "PI360 placement team" with
    no note. Which staff member acted is never shown."""
    out = []
    for e in r.events.select_related("reason").all():
        if e.from_stage == "":
            continue  # staff preparing the referral
        if e.kind == StageEvent.CORRECTION:
            continue  # internal fix-ups
        own = e.actor_id in people
        out.append(
            {
                "to": e.to_stage,
                "label": EMPLOYER_LABELS.get(e.to_stage, STAGE_NAMES.get(e.to_stage, e.to_stage)),
                "at": e.at.isoformat(),
                "by": people[e.actor_id] if own else STAFF_TEAM,
                "own": own,
                "reason": e.reason.name if own and e.reason_id else "",
                "note": e.note if own else "",
            }
        )
    return out


def _can_move_to(r) -> list[str]:
    return [s for s in services.next_stages(r) if s in EMPLOYER_MOVES]


def own_referral(employer_id, pk, *, people) -> dict:
    r = _referral(employer_id, pk)
    return {
        **_summary(r),
        "interview": {
            "at": r.interview_at.isoformat() if r.interview_at else None,
            "place": r.interview_place,
            "note": r.interview_note,
        },
        "can_move_to": _can_move_to(r),
        "can_set_interview": r.stage == Referral.INTERVIEW,
        "contact_visible": _contact_visible(r),
        "history": _history(r, people),
    }


def own_reasons() -> list[dict]:
    """Why a company may decline a candidate."""
    return [
        {"id": x["id"], "name": x["name"], "needs_note": x["needs_note"]}
        for x in configuration.referral_reasons(Referral.REJECTED)
    ]


def move_own_referral(*, actor, employer_id, pk, to, reason_id=None, note="", people) -> dict:
    r = _referral(employer_id, pk)
    if to not in EMPLOYER_MOVES:
        raise services.RuleViolation(
            "to", "Only the PI360 placement team can make this change.", "staff_only"
        )
    services.transition(actor=actor, referral=r, to=to, reason_id=reason_id, note=note)
    return own_referral(employer_id, pk, people=people)


def set_own_interview(*, actor, employer_id, pk, at, place="", note="", people) -> dict:
    r = _referral(employer_id, pk)
    services.set_interview(actor=actor, referral=r, at=at, place=place, note=note)
    return own_referral(employer_id, pk, people=people)


# ---- the candidate's CV ----------------------------------------------------------------------


def _candidate(employer_id, pk):
    r = _referral(employer_id, pk)
    p = participants.find_active(r.participant_id)
    if p is None:
        raise Missing
    return r, p


def own_cv(employer_id, pk) -> dict:
    """The CV document for a candidate the company was referred. Without contact details until
    selected, and without the profile-completeness hints written for the youth."""
    r, p = _candidate(employer_id, pk)
    doc = participants.build_cv(p, include_contact=_contact_visible(r))
    doc.pop("completeness", None)
    return {**doc, "contact_visible": _contact_visible(r)}


def own_cv_pdf(*, actor, employer_id, pk) -> tuple[bytes, str]:
    r, p = _candidate(employer_id, pk)
    return participants.cv_pdf(actor=actor, p=p, include_contact=_contact_visible(r))


def own_photo(employer_id, pk) -> bytes | None:
    _, p = _candidate(employer_id, pk)
    return participants.get_photo(p)
