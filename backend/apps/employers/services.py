"""Public interface of apps.employers (T-044). Every change is audited in the same transaction."""

from difflib import SequenceMatcher

from django.db import transaction

from apps.audit import services as audit
from apps.configuration.services import normalise as norm

from .models import Employer, EmployerContact

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
