"""Public interface of apps.employers (T-044). Every change is audited in the same transaction."""

from datetime import date
from difflib import SequenceMatcher

from django.db import transaction

from apps.audit import services as audit
from apps.configuration.services import normalise as norm

from .models import Employer, EmployerContact, Opportunity, OpportunityRequirement

SIMILAR = (
    0.88  # name similarity that triggers the duplicate warning; steward decides, never auto-merged
)
FIELDS = ("name", "sector_id", "county_id", "sub_county", "address", "website", "status", "notes")


class DuplicateWarning(Exception):
    def __init__(self, matches):
        self.matches = matches


def find_similar(name, *, exclude=None):
    """Existing employers whose name is the same after normalising, or nearly so."""
    key = norm(name)
    if not key:
        return []
    out = []
    for e in Employer.objects.exclude(pk=exclude):
        ratio = (
            1.0
            if e.name_normalised == key
            else SequenceMatcher(None, key, e.name_normalised).ratio()
        )
        if ratio >= SIMILAR:
            out.append(
                {"id": str(e.pk), "name": e.name, "status": e.status, "score": round(ratio, 2)}
            )
    return sorted(out, key=lambda m: -m["score"])


def _snapshot(e):
    return {f: (str(getattr(e, f)) if getattr(e, f) is not None else None) for f in FIELDS}


@transaction.atomic
def create_employer(*, actor, data, confirm_duplicate=False):
    if not confirm_duplicate and (matches := find_similar(data["name"])):
        raise DuplicateWarning(matches)
    e = Employer.objects.create(**data)
    audit.record(
        actor=actor, action="employer.created", object_type="employer", object_id=e.pk,
        after=_snapshot(e),
    )  # fmt: skip
    return e


@transaction.atomic
def update_employer(*, actor, employer, data, confirm_duplicate=False):
    if (
        "name" in data
        and norm(data["name"]) != employer.name_normalised
        and not confirm_duplicate
        and (matches := find_similar(data["name"], exclude=employer.pk))
    ):
        raise DuplicateWarning(matches)
    before = _snapshot(employer)
    for k, v in data.items():
        setattr(employer, k, v)
    employer.save()
    after = _snapshot(employer)
    changed = [k for k in after if after[k] != before[k]]
    if changed:
        audit.record(
            actor=actor, action="employer.updated", object_type="employer", object_id=employer.pk,
            before={k: before[k] for k in changed}, after={k: after[k] for k in changed},
        )  # fmt: skip
    return employer


@transaction.atomic
def save_contact(*, actor, employer, data, contact=None):
    """Create or update a contact; making one primary demotes the previous primary."""
    if data.get("is_primary"):
        employer.contacts.exclude(pk=getattr(contact, "pk", None)).update(is_primary=False)
    if contact is None:
        contact = EmployerContact.objects.create(employer=employer, **data)
        action, before = "employer.contact_added", None
    else:
        before = {k: getattr(contact, k) for k in data}
        for k, v in data.items():
            setattr(contact, k, v)
        contact.save()
        action = "employer.contact_updated"
    audit.record(
        actor=actor, action=action, object_type="employer", object_id=employer.pk,
        before=before, after={"contact": str(contact.pk), **data},
    )  # fmt: skip
    return contact


@transaction.atomic
def remove_contact(*, actor, employer, contact):
    snap = {"contact": str(contact.pk), "name": contact.name}
    contact.delete()
    audit.record(
        actor=actor, action="employer.contact_removed", object_type="employer",
        object_id=employer.pk, before=snap,
    )  # fmt: skip


def history(employer):
    return audit.history("employer", employer.pk)


# --- opportunities (T-045, FR-12..FR-15) -----------------------------------------------------

OPP_FIELDS = (
    "title", "kind", "sector_id", "county_id", "location", "positions", "description",
    "start_date", "closing_date",
)  # fmt: skip


class RuleViolation(Exception):
    def __init__(self, field, message, code):
        super().__init__(message)
        self.field, self.message, self.code = field, message, code


def _opp_snapshot(o):
    return {f: (None if getattr(o, f) is None else str(getattr(o, f))) for f in OPP_FIELDS}


def _check_dates(start, closing):
    if start and closing and closing < start:
        raise RuleViolation("closing_date", "Closing date is before the start date.", "bad_dates")


@transaction.atomic
def create_opportunity(*, actor, employer, data):
    if employer.status == Employer.INACTIVE:
        raise RuleViolation("employer", "Employer is inactive.", "employer_inactive")
    _check_dates(data.get("start_date"), data.get("closing_date"))
    o = Opportunity.objects.create(employer=employer, **data)
    audit.record(
        actor=actor, action="opportunity.created", object_type="opportunity", object_id=o.pk,
        after={"employer": str(employer.pk), **_opp_snapshot(o)},
    )  # fmt: skip
    return o


@transaction.atomic
def update_opportunity(*, actor, opportunity, data):
    if opportunity.status in (Opportunity.CLOSED, Opportunity.EXPIRED):
        raise RuleViolation("status", "Reopen the opportunity before editing it.", "locked")
    merged = {**{f: getattr(opportunity, f) for f in ("start_date", "closing_date")}, **data}
    _check_dates(merged["start_date"], merged["closing_date"])
    if (
        opportunity.status == Opportunity.OPEN
        and merged["closing_date"]
        and merged["closing_date"] < date.today()
    ):
        raise RuleViolation("closing_date", "Closing date is in the past.", "past_closing")
    before = _opp_snapshot(opportunity)
    for k, v in data.items():
        setattr(opportunity, k, v)
    opportunity.save()
    after = _opp_snapshot(opportunity)
    changed = [k for k in after if after[k] != before[k]]
    if changed:
        audit.record(
            actor=actor, action="opportunity.updated", object_type="opportunity",
            object_id=opportunity.pk,
            before={k: before[k] for k in changed}, after={k: after[k] for k in changed},
        )  # fmt: skip
    return opportunity


@transaction.atomic
def transition(*, actor, opportunity, to, reason="", today=None):
    """Move an opportunity along the state machine; opening needs a future closing date."""
    today = today or date.today()
    if to not in Opportunity.TRANSITIONS.get(opportunity.status, set()):
        raise RuleViolation(
            "status", f"Cannot go from {opportunity.status} to {to}.", "bad_transition"
        )
    if to == Opportunity.OPEN:
        if opportunity.employer.status == Employer.INACTIVE:
            raise RuleViolation("employer", "Employer is inactive.", "employer_inactive")
        if not opportunity.closing_date or opportunity.closing_date < today:
            raise RuleViolation(
                "closing_date", "Set a closing date in the future before opening.", "closing_date"
            )
    before = opportunity.status
    opportunity.status = to
    opportunity.save(update_fields=["status", "updated_at"])
    audit.record(
        actor=actor, action=f"opportunity.{to}", object_type="opportunity",
        object_id=opportunity.pk, before={"status": before}, after={"status": to}, reason=reason,
    )  # fmt: skip
    return opportunity


def expire_due(*, today=None):
    """Scheduled job: open opportunities past their closing date become expired. Idempotent."""
    today = today or date.today()
    due = Opportunity.objects.filter(status=Opportunity.OPEN, closing_date__lt=today)
    n = 0
    for o in due:
        transition(actor=None, opportunity=o, to=Opportunity.EXPIRED, reason="closing date passed")
        n += 1
    return n


def accepts_referrals(opportunity_id) -> bool:
    """For the referral workflow (T-046): only an open, not-yet-past opportunity takes referrals."""
    return Opportunity.objects.filter(
        pk=opportunity_id, status=Opportunity.OPEN, closing_date__gte=date.today()
    ).exists()


@transaction.atomic
def save_requirement(*, actor, opportunity, data, requirement=None):
    if opportunity.status in (Opportunity.CLOSED, Opportunity.EXPIRED):
        raise RuleViolation("status", "Reopen the opportunity before editing it.", "locked")
    if requirement is None:
        requirement = OpportunityRequirement.objects.create(opportunity=opportunity, **data)
        action, before = "opportunity.requirement_added", None
    else:
        before = {k: getattr(requirement, k) for k in data}
        for k, v in data.items():
            setattr(requirement, k, v)
        requirement.save()
        action = "opportunity.requirement_updated"
    audit.record(
        actor=actor, action=action, object_type="opportunity", object_id=opportunity.pk,
        before=before, after={"requirement": str(requirement.pk), **data},
    )  # fmt: skip
    return requirement


@transaction.atomic
def remove_requirement(*, actor, opportunity, requirement):
    if opportunity.status in (Opportunity.CLOSED, Opportunity.EXPIRED):
        raise RuleViolation("status", "Reopen the opportunity before editing it.", "locked")
    snap = {"requirement": str(requirement.pk), "description": requirement.description}
    requirement.delete()
    audit.record(
        actor=actor, action="opportunity.requirement_removed", object_type="opportunity",
        object_id=opportunity.pk, before=snap,
    )  # fmt: skip


def opportunity_history(opportunity):
    return audit.history("opportunity", opportunity.pk)
