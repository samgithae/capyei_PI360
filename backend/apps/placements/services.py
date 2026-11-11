"""Public interface of apps.placements. Other modules import only this module (doc 04 §4).

    from apps.placements import services as placements
    placements.record(actor=u, enrollment_id=e, source_status="Employment", ...)

History is append-only: ``record`` adds a row, ``review`` sets the reviewable fields. Every write
is audited in the same transaction."""

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit

from .models import Placement

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
