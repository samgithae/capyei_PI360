"""One company's own records, for the employer portal.

Every function takes the ``employer_id`` the portal resolved from the signed-in user's membership
and limits every query to it, so a caller can never reach another company's data by passing an id.
An id that is not this company's is "missing", exactly as if it did not exist.

These return plain dicts and take ids, never models, so the portal needs no model import. Never
included: the staff notes on the employer, the audit trail, other companies' records.

Import ``services`` (which re-exports everything here), never this module directly: ``services``
imports this at its end, and this imports ``services`` at its start.
"""

from datetime import timedelta

from django.db.models import Q

from apps.configuration import services as configuration

from . import services
from .models import Employer, EmployerContact, Opportunity, OpportunityRequirement

# The choices a company may send, so the portal never imports the models.
KIND_CHOICES = Opportunity.TYPES
FACTOR_CHOICES = OpportunityRequirement.FACTORS


class Missing(LookupError):
    """The record does not exist, or belongs to another company."""


# ---- the shapes both the staff API and the portal use ----------------------------------------


def refs(rows):
    """Linked reference rows as ``[{id, name}]``, by name."""
    return [{"id": str(r.pk), "name": r.name} for r in sorted(rows, key=lambda r: r.name)]


def contact_dict(c):
    return {
        "id": str(c.pk), "name": c.name, "role": c.role, "email": c.email,
        "phone": c.phone, "is_primary": c.is_primary,
    }  # fmt: skip


def requirement_dict(r):
    return {
        "id": str(r.pk), "factor": r.factor, "description": r.description,
        "is_mandatory": r.is_mandatory,
        "qualification_level_id": (
            str(r.qualification_level_id) if r.qualification_level_id else None
        ),
        "min_grade_id": str(r.min_grade_id) if r.min_grade_id else None,
        "skill_id": str(r.skill_id) if r.skill_id else None,
        "min_months": r.min_months,
        "needed_by": r.needed_by.isoformat() if r.needed_by else None,
        "work_pattern": r.work_pattern,
        "needs_structuring": r.needs_structuring,
    }  # fmt: skip


def publish_request_dict(o):
    """Where an approval stands: ``none``, ``pending`` (waiting for PI staff) or ``declined``."""
    if o.publish_requested_at:
        return {
            "state": "pending",
            "requested_at": o.publish_requested_at.isoformat(),
            "requested_by": o.publish_requested_by,
            "declined_reason": "",
        }
    if o.publish_declined_at:
        return {
            "state": "declined",
            "requested_at": None,
            "requested_by": "",
            "declined_at": o.publish_declined_at.isoformat(),
            "declined_reason": o.publish_declined_reason,
        }
    return {"state": "none", "requested_at": None, "requested_by": "", "declined_reason": ""}


def opportunity_summary(o):
    return {
        "id": str(o.pk),
        "title": o.title,
        "employer_id": str(o.employer_id),
        "employer": o.employer.name,
        "kind": o.kind,
        "status": o.status,
        "counties": refs(o.counties.all()),
        "sectors": refs(o.sectors.all()),
        "positions": o.positions,
        "closing_date": o.closing_date.isoformat() if o.closing_date else None,
        "archived": o.archived_at is not None,
        "publish_request": publish_request_dict(o),
    }


def opportunity_detail(o):
    return {
        **opportunity_summary(o),
        "sector_ids": [s["id"] for s in refs(o.sectors.all())],
        "county_ids": [c["id"] for c in refs(o.counties.all())],
        "location": o.location,
        "description": o.description,
        "start_date": o.start_date.isoformat() if o.start_date else None,
        "requirements": [requirement_dict(r) for r in o.requirements.all()],
        "requirement_options": {
            **{
                k: v
                for k, v in configuration.profile_options().items()
                if k not in ("sectors", "skills")
            },
            # Only the skills this opportunity already asks for; the picker searches the rest.
            "skills": list(
                configuration.skills_by_ids(
                    r.skill_id for r in o.requirements.all() if r.skill_id
                ).values()
            ),
            "work_patterns": [
                {"id": k, "name": n.capitalize()} for k, n in services.PATTERN_NAMES.items()
            ],
        },
    }


# ---- the company's profile and contacts -------------------------------------------------------

# What a company may change about itself. The name and the status stay with PI staff, and so do
# the notes, which only staff ever see.
PROFILE_FIELDS = ("sub_county", "address", "website", "sector_ids", "county_ids")


def _employer(employer_id):
    e = (
        Employer.objects.prefetch_related("sectors", "counties", "contacts")
        .filter(pk=employer_id, archived_at__isnull=True)
        .first()
    )
    if e is None:
        raise Missing
    return e


def own_profile(employer_id) -> dict:
    e = _employer(employer_id)
    options = configuration.profile_options()
    return {
        "id": str(e.pk),
        "name": e.name,
        "sectors": refs(e.sectors.all()),
        "counties": refs(e.counties.all()),
        "sector_ids": [s["id"] for s in refs(e.sectors.all())],
        "county_ids": [c["id"] for c in refs(e.counties.all())],
        "sub_county": e.sub_county,
        "address": e.address,
        "website": e.website,
        "contacts": [contact_dict(c) for c in e.contacts.all()],
        "options": {
            "sectors": options["sectors"],
            "counties": configuration.filter_options()["counties"],
        },
    }


def update_own_profile(*, actor, employer_id, data) -> dict:
    e = _employer(employer_id)
    clean = {k: v for k, v in data.items() if k in PROFILE_FIELDS}
    services.update_employer(actor=actor, employer=e, data=clean)
    return own_profile(employer_id)


def _contact(employer_id, contact_id):
    c = EmployerContact.objects.filter(employer_id=employer_id, pk=contact_id).first()
    if c is None:
        raise Missing
    return c


def contact_by_email(employer_id, email) -> dict | None:
    """The company's contact with this e-mail address, or None (case does not matter)."""
    wanted = (email or "").strip()
    if not wanted:
        return None
    c = EmployerContact.objects.filter(employer_id=employer_id, email__iexact=wanted).first()
    return contact_dict(c) if c else None


def own_contact(employer_id, contact_id) -> dict:
    return contact_dict(_contact(employer_id, contact_id))


def contacts_of(employer_id) -> list[dict]:
    """Everyone on the company's contact list, main contact first."""
    return [contact_dict(c) for c in EmployerContact.objects.filter(employer_id=employer_id)]


def save_own_contact(*, actor, employer_id, data, contact_id=None) -> dict:
    e = _employer(employer_id)
    contact = _contact(employer_id, contact_id) if contact_id else None
    c = services.save_contact(actor=actor, employer=e, data=data, contact=contact)
    return contact_dict(c)


def remove_own_contact(*, actor, employer_id, contact_id) -> None:
    e = _employer(employer_id)
    services.remove_contact(actor=actor, employer=e, contact=_contact(employer_id, contact_id))


# ---- the company's opportunities --------------------------------------------------------------


def _qs(employer_id):
    return (
        Opportunity.objects.filter(employer_id=employer_id, archived_at__isnull=True)
        .select_related("employer")
        .prefetch_related("sectors", "counties")
    )


def _opportunity(employer_id, pk):
    try:
        o = _qs(employer_id).filter(pk=pk).first()
    except (ValueError, TypeError):
        o = None
    if o is None:
        raise Missing
    return o


CLOSING_SOON_DAYS = 7
VIEWS = ("open", "closing_soon", "expired", "awaiting", "declined")


def _view(qs, view, today):
    """Named lists the dashboard counts and links to. The figure and the list behind it use this
    one function, so they cannot disagree."""
    if view == "open":
        return qs.filter(status=Opportunity.OPEN).filter(
            Q(closing_date__isnull=True) | Q(closing_date__gte=today)
        )
    if view == "closing_soon":
        return qs.filter(
            status=Opportunity.OPEN,
            closing_date__gte=today,
            closing_date__lte=today + timedelta(days=CLOSING_SOON_DAYS),
        )
    if view == "expired":
        return qs.filter(
            Q(status=Opportunity.EXPIRED) | Q(status=Opportunity.OPEN, closing_date__lt=today)
        )
    if view == "awaiting":
        return qs.filter(status=Opportunity.DRAFT, publish_requested_at__isnull=False)
    if view == "declined":
        return qs.filter(
            status=Opportunity.DRAFT,
            publish_requested_at__isnull=True,
            publish_declined_at__isnull=False,
        )
    return qs


def own_opportunities(employer_id, *, status="", q="", view="", offset=0, size=25, today) -> dict:
    qs = _qs(employer_id)
    if status in {s for s, _ in Opportunity.STATUSES}:
        qs = qs.filter(status=status)
    if view in VIEWS:
        qs = _view(qs, view, today)
    if q.strip():
        qs = qs.filter(title__icontains=q.strip())
    return {
        "total": qs.count(),
        "page_size": size,
        "results": [opportunity_summary(o) for o in qs[offset : offset + size]],
    }


def opportunity_figures(employer_id, today) -> dict:
    """How many opportunities each named list holds, for the dashboard."""
    base = _qs(employer_id)
    return {v: _view(base, v, today).count() for v in VIEWS}


def own_opportunity(employer_id, pk) -> dict:
    return opportunity_detail(_opportunity(employer_id, pk))


def create_own_opportunity(*, actor, employer_id, data) -> dict:
    e = _employer(employer_id)
    o = services.create_opportunity(actor=actor, employer=e, data=data)
    return own_opportunity(employer_id, o.pk)


def update_own_opportunity(*, actor, employer_id, pk, data) -> dict:
    services.update_opportunity(actor=actor, opportunity=_opportunity(employer_id, pk), data=data)
    return own_opportunity(employer_id, pk)


def move_own_opportunity(*, actor, employer_id, pk, to, publish_directly, label="") -> dict:
    """``to`` is ``open``, ``closed`` or ``withdraw`` (take back a publish request). When the
    company may not publish on its own, ``open`` becomes a request for PI staff to approve."""
    o = _opportunity(employer_id, pk)
    if to == "withdraw":
        services.withdraw_publish_request(actor=actor, opportunity=o)
    elif to == Opportunity.OPEN and not publish_directly:
        services.request_publish(actor=actor, opportunity=o, label=label)
    else:
        services.transition(actor=actor, opportunity=o, to=to)
    return own_opportunity(employer_id, pk)


# ---- requirements -----------------------------------------------------------------------------


def _requirement(opportunity, requirement_id):
    try:
        return opportunity.requirements.get(pk=requirement_id)
    except (OpportunityRequirement.DoesNotExist, ValueError):
        raise Missing from None


def save_own_requirement(*, actor, employer_id, pk, data, requirement_id=None) -> dict:
    o = _opportunity(employer_id, pk)
    r = _requirement(o, requirement_id) if requirement_id else None
    return requirement_dict(
        services.save_requirement(actor=actor, opportunity=o, data=data, requirement=r)
    )


def remove_own_requirement(*, actor, employer_id, pk, requirement_id) -> None:
    o = _opportunity(employer_id, pk)
    services.remove_requirement(
        actor=actor, opportunity=o, requirement=_requirement(o, requirement_id)
    )


def sync_own_skills(*, actor, employer_id, pk, items) -> dict:
    o = _opportunity(employer_id, pk)
    rows = services.sync_skill_requirements(actor=actor, opportunity=o, items=items)
    return {"requirements": [requirement_dict(r) for r in rows]}
