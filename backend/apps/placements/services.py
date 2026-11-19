"""Public interface of apps.placements. Other modules import only this module (doc 04 §4).

    from apps.placements import services as placements
    placements.record(actor=u, enrollment_id=e, source_status="Employment", ...)

History is append-only: ``record`` adds a row, ``review`` sets the reviewable fields. Every write
is audited in the same transaction."""

import html
from collections import Counter

from django.db import transaction
from django.db.models import Q
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
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "exit_reason": p.exit_reason,
        "verification_source": p.verification_source,
        "verified": p.verified_on is not None,
    }


SOURCES = {code for code, _ in Placement.SOURCES}
PLACED = "placed"
# Wording for an episode a staff member enters by hand (no source file said anything).
MANUAL_SOURCE_STATUS = "Entered by staff"


def _check_dates(start_date, end_date):
    if end_date and not start_date:
        raise PlacementError("Give the start date before the end date.")
    if start_date and end_date and end_date < start_date:
        raise PlacementError("The end date cannot be before the start date.")


@transaction.atomic
def record(
    *,
    actor,
    enrollment_id,
    source_status: str,
    employer_name_source: str = "",
    designation: str = "",
    start_date=None,
    end_date=None,
    exit_reason: str = "",
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
    _check_dates(start_date, end_date)
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
        end_date=end_date,
        exit_reason=exit_reason.strip(),
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


# --- Episodes entered and kept by staff (T-065, FR-23/FR-24) -----------------------------------

EDITABLE_BY_STAFF = ("employer_id", "employer_name_source", "designation", "start_date", "benefits")


def get(placement_id) -> Placement:
    try:
        return Placement.objects.select_related("employer").get(pk=placement_id)
    except (Placement.DoesNotExist, ValueError, TypeError):  # ValueError: not a UUID
        raise PlacementError("That placement does not exist.") from None


def list_for(enrollment_ids, *, pathway="", state="", employer_id=None, q="", q_enrollment_ids=()):
    """Episodes for the given enrollments, newest first (a queryset). ``state``: current, ended
    or unverified. ``q`` matches employer or designation; ``q_enrollment_ids`` adds enrollments
    whose youth matched the same search by name."""
    rows = Placement.objects.filter(enrollment_id__in=list(enrollment_ids)).select_related(
        "employer"
    )
    if pathway:
        rows = rows.filter(pathway=pathway)
    if employer_id:
        rows = rows.filter(employer_id=employer_id)
    if q:
        rows = rows.filter(
            Q(employer_name_source__icontains=q)
            | Q(employer__name__icontains=q)
            | Q(designation__icontains=q)
            | Q(enrollment_id__in=list(q_enrollment_ids))
        )
    if state == "current":
        rows = rows.filter(status=PLACED, end_date__isnull=True)
    elif state == "ended":
        rows = rows.filter(end_date__isnull=False)
    elif state == "unverified":
        rows = rows.filter(verified_on__isnull=True)
    return rows


def unverified_count(enrollment_ids) -> int:
    """Placed episodes nobody has verified yet, for the work queue."""
    return Placement.objects.filter(
        enrollment_id__in=list(enrollment_ids), status=PLACED, verified_on__isnull=True
    ).count()


def is_current(p: Placement) -> bool:
    return p.status == PLACED and p.end_date is None


def current_by_enrollment(enrollment_ids) -> dict:
    """The newest running placed episode for each enrollment that has one."""
    out: dict = {}
    rows = Placement.objects.filter(
        enrollment_id__in=list(enrollment_ids), status=PLACED, end_date__isnull=True
    ).select_related("employer")
    for p in rows:  # the model orders newest first, so the first one seen wins
        out.setdefault(p.enrollment_id, p)
    return out


def _same_words(text) -> str:
    return " ".join((text or "").lower().split())


def running_with_employer(enrollment_id, *, employer_id=None, employer_name="") -> Placement | None:
    """The youth's running placement with this employer, if any: the same register employer,
    or (for one typed by name) the same name ignoring case and spacing. Used to warn before a
    second episode is recorded by mistake; ended episodes never count."""
    running = Placement.objects.filter(
        enrollment_id=enrollment_id, status=PLACED, end_date__isnull=True
    ).select_related("employer")
    name = _same_words(employer_name)
    for p in running:
        if employer_id and p.employer_id and str(p.employer_id) == str(employer_id):
            return p
        if not employer_id and name:
            if name in (
                _same_words(p.employer_name_source),
                _same_words(p.employer and p.employer.name),
            ):
                return p
    return None


@transaction.atomic
def record_manual(
    *,
    actor,
    enrollment_id,
    pathway: str,
    start_date,
    employer_id=None,
    employer_name_source: str = "",
    designation: str = "",
    end_date=None,
    exit_reason: str = "",
    benefits: str = "",
) -> Placement:
    """A placement a staff member observed and entered (a call, a visit). Always a real
    placement: the pathway is required and the status is 'placed'."""
    if not pathway:
        raise PlacementError("Choose the pathway.")
    if start_date is None:
        raise PlacementError("Give the date it started.")
    if not employer_id and not employer_name_source.strip() and pathway in (Placement.WAGE,):
        raise PlacementError("Say who the employer is.")
    p = record(
        actor=actor, enrollment_id=enrollment_id, source_status=MANUAL_SOURCE_STATUS,
        pathway=pathway, status=PLACED, employer_id=employer_id,
        employer_name_source=employer_name_source, designation=designation,
        start_date=start_date, end_date=end_date, exit_reason=exit_reason, benefits=benefits,
    )  # fmt: skip
    _followups.generate_for(p, actor=actor)  # FR-25: the check-ins start with the placement
    return p


def _save_reviewed(p: Placement, *, actor, action: str, before: dict, reset_verification: bool):
    if reset_verification and p.verified_on:
        p.verified_by, p.verified_on, p.verification_source = None, None, ""
    p.save(update_fields=sorted(Placement.REVIEWABLE))
    audit.record(
        actor=actor, action=action, object_type="placement", object_id=p.pk,
        before=before, after=_snapshot(p),
    )  # fmt: skip
    return p


@transaction.atomic
def update_episode(*, actor, placement_id, **changes) -> Placement:
    """Correct the facts of an episode staff entered. An imported episode stays as reported (its
    employer link is a steward's review). Changing a verified episode clears its verification."""
    p = Placement.objects.select_for_update().get(pk=placement_id)
    if p.source_row_id is not None:
        raise PlacementError("An imported placement stays as reported; use review to link it.")
    unknown = set(changes) - set(EDITABLE_BY_STAFF) - {"pathway"}
    if unknown:
        raise PlacementError(f"Cannot change: {', '.join(sorted(unknown))}.")
    before = _snapshot(p)
    if "pathway" in changes:
        if changes["pathway"] not in PATHWAYS:
            raise PlacementError("Choose the pathway.")
        p.pathway = changes["pathway"]
    for field in ("employer_name_source", "designation", "benefits"):
        if field in changes:
            setattr(p, field, (changes[field] or "").strip())
    if "employer_id" in changes:
        p.employer_id = changes["employer_id"] or None
    if "start_date" in changes:
        if changes["start_date"] is None:
            raise PlacementError("Give the date it started.")
        p.start_date = changes["start_date"]
    _check_dates(p.start_date, p.end_date)
    return _save_reviewed(
        p, actor=actor, action="placement.updated", before=before, reset_verification=True
    )


@transaction.atomic
def end_episode(*, actor, placement_id, end_date, exit_reason: str = "") -> Placement:
    """Close a running episode (FR-24). A later job is a new episode beside it. Ending is allowed
    on an imported episode too: it adds the end the source never said."""
    p = Placement.objects.select_for_update().get(pk=placement_id)
    if p.end_date is not None:
        raise PlacementError("This placement has already ended.")
    if end_date is None:
        raise PlacementError("Give the date it ended.")
    before = _snapshot(p)
    p.end_date, p.exit_reason = end_date, exit_reason.strip()
    _check_dates(p.start_date, p.end_date)
    return _save_reviewed(
        p, actor=actor, action="placement.ended", before=before, reset_verification=False
    )


@transaction.atomic
def verify_episode(*, actor, placement_id, source: str) -> Placement:
    """Record that staff confirmed the episode and how (FR-23)."""
    if source not in SOURCES:
        raise PlacementError("Say how it was confirmed.")
    p = Placement.objects.select_for_update().get(pk=placement_id)
    if not p.pathway or not p.status:
        raise PlacementError("Set the pathway and status before verifying.")
    before = _snapshot(p)
    p.verified_by, p.verified_on, p.verification_source = actor, timezone.now(), source
    _save_reviewed(
        p, actor=actor, action="placement.verified", before=before, reset_verification=False
    )
    _followups.generate_for(p, actor=actor)  # confirmation also starts them (imported episodes)
    return p


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


def for_enrollments(enrollment_ids) -> list[dict]:
    """Verified-or-imported placements that were mapped as a real placement, for the learner's
    own page. Only facts, no review notes."""
    rows = Placement.objects.filter(enrollment_id__in=list(enrollment_ids), status="placed")
    return [
        {
            "id": str(p.id),
            "employer": p.employer.name if p.employer_id else p.employer_name_source,
            "designation": p.designation,
            "pathway": p.get_pathway_display() if p.pathway else "",
            "start_date": p.start_date.isoformat() if p.start_date else None,
        }
        for p in rows.select_related("employer")
    ]


# --- for reporting (T-070) -------------------------------------------------------------------


def placed_facts() -> list[dict]:
    """Every placement mapped as a real placement: which enrollment and when it started."""
    return [
        {"enrollment_id": e, "on": d or c.date()}
        for e, d, c in Placement.objects.filter(status="placed").values_list(
            "enrollment_id", "start_date", "created_at"
        )
    ]


# ---- follow-up scheduling (T-066) -------------------------------------------------------------
# Imported last: followups.py imports names defined above, so this stays at the end of the file.
from . import followups as _followups  # noqa: E402

DUE_SOON_DAYS = _followups.DUE_SOON_DAYS
FollowUpError = _followups.FollowUpError
FollowUp = _followups.FollowUp
FollowUpAttempt = _followups.FollowUpAttempt
FollowUpStep = _followups.FollowUpStep
followup_assign = _followups.assign
followup_attempts = _followups.attempts_of
followup_cancel = _followups.cancel
followup_complete = _followups.complete
followup_counts = _followups.counts
followup_create_step = _followups.create_step
followup_get = _followups.get
followup_history = _followups.history
followup_is_overdue = _followups.is_overdue
followup_list = _followups.list_for
followup_log_attempt = _followups.log_attempt
followup_retention_counts = _followups.retention_counts
followup_steps = _followups.steps
followup_unreachable = _followups.mark_unreachable
followup_update_step = _followups.update_step
generate_followups = _followups.generate_for
