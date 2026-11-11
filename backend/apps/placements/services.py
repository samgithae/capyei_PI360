"""Public interface of apps.placements. Other modules import only this module (doc 04 §4).

    from apps.placements import services as placements
    placements.record(actor=u, enrollment_id=e, source_status="Employment", ...)

History is append-only: ``record`` adds a row, ``review`` sets the reviewable fields. Every write
is audited in the same transaction."""

import html
from collections import Counter

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.configuration.services import normalise

from .models import Placement, PlacementStatusMapping

PATHWAYS = {code for code, _ in Placement.PATHWAYS}


class PlacementError(ValueError):
    """The request is not valid; the message is safe to show the user."""


def _snapshot(p: Placement) -> dict:
    return {
        "enrollment": str(p.enrollment_id),
        "employer": str(p.employer_id) if p.employer_id else None,
        "pathway": p.pathway,
        "status": p.status,
        "source_status": p.source_status,
    }


@transaction.atomic
def record(
    *,
    actor,
    enrollment_id,
    source_status: str,
    employer_name_source: str = "",
    designation: str = "",
    start_date=None,
    benefits: str = "",
    pathway: str = "",
    status: str = "",
    employer_id=None,
    source_row_id=None,
) -> Placement:
    """Append one placement episode. ``source_status`` is required: it is what was reported."""
    if not source_status.strip():
        raise PlacementError("A placement needs the status as reported by the source.")
    if pathway and pathway not in PATHWAYS:
        raise PlacementError(f"Unknown pathway '{pathway}'.")
    if not pathway and not status and (m := resolve_status(source_status)) and m.is_placement:
        pathway, status = m.pathway, m.status  # unmapped values stay blank: held for a steward
    enrollment_model = Placement._meta.get_field("enrollment").related_model
    if not enrollment_model.objects.filter(pk=enrollment_id).exists():
        raise PlacementError("That enrollment does not exist.")
    placement = Placement.objects.create(
        enrollment_id=enrollment_id,
        employer_id=employer_id,
        employer_name_source=employer_name_source.strip(),
        designation=designation.strip(),
        source_status=source_status.strip(),
        pathway=pathway,
        status=status,
        start_date=start_date,
        benefits=benefits.strip(),
        source_row_id=source_row_id,
    )
    audit.record(
        actor=actor,
        action="placement.recorded",
        object_type="placement",
        object_id=placement.pk,
        after=_snapshot(placement),
    )
    return placement


@transaction.atomic
def review(
    *, actor, placement_id, employer_id=None, pathway=None, status=None, verified=False
) -> Placement:
    """A steward's review: link the employer, set pathway or status, and optionally verify."""
    placement = Placement.objects.select_for_update().get(pk=placement_id)
    before = _snapshot(placement)
    if pathway is not None:
        if pathway and pathway not in PATHWAYS:
            raise PlacementError(f"Unknown pathway '{pathway}'.")
        placement.pathway = pathway
    if status is not None:
        placement.status = status
    if employer_id is not None:
        placement.employer_id = employer_id
    if verified:
        placement.verified_by = actor
        placement.verified_on = timezone.now()
    placement.save(update_fields=sorted(Placement.REVIEWABLE))
    audit.record(
        actor=actor,
        action="placement.reviewed",
        object_type="placement",
        object_id=placement.pk,
        before=before,
        after=_snapshot(placement),
    )
    return placement


def for_enrollment(enrollment_id) -> list[Placement]:
    """Newest first."""
    return list(Placement.objects.filter(enrollment_id=enrollment_id))


# --- Status mapping (T-087 stage C, D-061) -----------------------------------------------------

# The D-061 proposal from doc 14 §6. Never loaded automatically: a steward chooses to load it.
PROPOSED = [
    ("Employment", Placement.WAGE, "placed", True),
    ("Entrepreneur", Placement.SELF, "placed", True),
    ("Further Studies", Placement.TRAINING, "placed", True),
    ("Opportunities shows&Rejected", "", "declined", False),
]


def status_key(text) -> str:
    """Grouping key for a status value: HTML escapes undone, case and punctuation ignored, so the
    two source spellings of 'shows&Rejected' meet."""
    return normalise(html.unescape(text or ""))


def resolve_status(source_value):
    """The mapping for a source value, or None. A blank value never maps (rows stay held)."""
    key = status_key(source_value)
    return PlacementStatusMapping.objects.filter(source_key=key).first() if key else None


def unmapped_values(values) -> list[dict]:
    """Distinct non-blank values with no mapping, most frequent first: the 'map these' list."""
    counts, shown = Counter(), {}
    for v in values:
        key = status_key(v)
        if key and resolve_status(v) is None:
            counts[key] += 1
            shown.setdefault(key, v.strip())
    return [{"value": shown[k], "count": n} for k, n in counts.most_common()]


@transaction.atomic
def map_status(*, actor, source_value, status, pathway="", is_placement=True):
    """Create or change the meaning of a source value; a change bumps the version."""
    key = status_key(source_value)
    if not key:
        raise PlacementError("A blank value cannot be mapped.")
    if not status.strip():
        raise PlacementError("Give the status this value means.")
    if pathway and pathway not in PATHWAYS:
        raise PlacementError(f"Unknown pathway '{pathway}'.")
    if is_placement and not pathway:
        raise PlacementError("A value that counts as a placement needs a pathway.")
    m = PlacementStatusMapping.objects.filter(source_key=key).first()
    before = (
        {"pathway": m.pathway, "status": m.status, "is_placement": m.is_placement} if m else None
    )
    if m is None:
        m = PlacementStatusMapping(source_value=source_value.strip(), source_key=key)
    else:
        m.version += 1
    m.pathway, m.status, m.is_placement, m.mapped_by = pathway, status.strip(), is_placement, actor
    m.save()
    audit.record(
        actor=actor, action="placement.status_mapped", object_type="placement_status_mapping",
        object_id=m.pk, before=before,
        after={"pathway": m.pathway, "status": m.status, "is_placement": m.is_placement},
    )  # fmt: skip
    return m


@transaction.atomic
def load_proposed(*, actor) -> int:
    """Load the D-061 proposal for values not yet mapped; never overwrites a steward's choice."""
    n = 0
    for value, pathway, status, is_placement in PROPOSED:
        if resolve_status(value) is None:
            map_status(
                actor=actor, source_value=value, status=status, pathway=pathway,
                is_placement=is_placement,
            )  # fmt: skip
            n += 1
    return n


@transaction.atomic
def apply_mappings(*, actor) -> int:
    """Fill pathway and status on earlier placements that were recorded while unmapped. Only
    blank fields are filled; a reviewed value is never changed. Returns how many were updated."""
    n = 0
    for p in Placement.objects.filter(status="").select_for_update():
        m = resolve_status(p.source_status)
        if m is None or not m.is_placement:
            continue
        p.status, p.pathway = m.status, p.pathway or m.pathway
        p.save(update_fields=sorted(Placement.REVIEWABLE))
        n += 1
    if n:
        audit.record(
            actor=actor, action="placement.mappings_applied", object_type="placement",
            object_id="bulk", after={"updated": n},
        )  # fmt: skip
    return n


@transaction.atomic
def undo_import(*, actor, placement_ids) -> int:
    """Remove placements an import created, when that import is rolled back. This is the only
    way a placement is deleted; a verified one is refused."""
    rows = Placement.objects.filter(pk__in=list(placement_ids))
    if rows.filter(verified_on__isnull=False).exists():
        raise PlacementError("A verified placement cannot be rolled back.")
    n = rows.count()
    rows.delete()  # queryset delete: Placement.delete() is blocked for everyone else
    if n:
        audit.record(
            actor=actor, action="placement.import_undone", object_type="placement",
            object_id="bulk", after={"removed": n},
        )  # fmt: skip
    return n
