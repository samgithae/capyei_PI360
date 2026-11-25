"""Public interface of apps.placements. Other modules import only this module (doc 04 §4).

    from apps.placements import services as placements
    placements.record(actor=u, enrollment_id=e, source_status="Employment", ...)

History is append-only: ``record`` adds a row, ``review`` sets the reviewable fields. Every write
is audited in the same transaction."""

import html
from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit import services as audit
from apps.configuration import services as configuration
from apps.configuration.services import normalise

from .models import ExitFeedback, Placement, PlacementStatusMapping

PATHWAYS = {code for code, _ in Placement.PATHWAYS}


class PlacementError(ValueError):
    """The request is not valid; the message is safe to show the user."""


class ActivePlacementExists(PlacementError):
    """D-081 (PI360-NEW-070): a youth has at most one running placement. ``running`` is the one
    that is already running, so the caller can name it and offer "changed employer"."""

    def __init__(self, running):
        self.running = running
        who = running.employer.name if running.employer_id else running.employer_name_source
        since = running.start_date.strftime("%d %b %Y") if running.start_date else "an unknown date"
        super().__init__(
            f"This youth already has a running placement{f' with {who}' if who else ''}, "
            f"since {since}. End it first, or use Changed employer."
        )


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
        # NEW-071. Income is G9 economic data: the audit trail says only whether it is recorded,
        # so placement history (placements.view) never shows the amount.
        "business_activity": p.business_activity,
        "operational_status": p.operational_status,
        "business_evidence": p.business_evidence,
        "income_recorded": p.monthly_income is not None,
        "duplicate_of": str(p.duplicate_of_id) if p.duplicate_of_id else None,
        # NEW-035. Salary and band are economic data: only whether one is recorded.
        "employment_type": str(p.employment_type_id) if p.employment_type_id else None,
        "salary_recorded": p.salary_amount is not None or p.salary_band_id is not None,
        "previous_placement": str(p.previous_placement_id) if p.previous_placement_id else None,
    }


SOURCES = {code for code, _ in Placement.SOURCES}
PLACED = "placed"
# Wording for an episode a staff member enters by hand (no source file said anything).
MANUAL_SOURCE_STATUS = "Entered by staff"


# "Running" (D-081): mapped as placed and not ended. One per youth, across all their enrollments.
RUNNING = Q(status="placed", end_date__isnull=True)


def _enrollment_model():
    return Placement._meta.get_field("enrollment").related_model


def youth_of(enrollment_id):
    """The id of the youth who owns this enrollment, or None."""
    return (
        _enrollment_model()
        .objects.filter(pk=enrollment_id)
        .values_list("participant_id", flat=True)
        .first()
    )


def running_for_youth(enrollment_id, *, exclude=None, lock=False) -> Placement | None:
    """The running placement of the youth who owns this enrollment, on any of their enrollments.
    ``lock`` holds the youth's row until the transaction ends, so two officers saving at the same
    moment cannot both create one. The database also refuses two on one enrollment."""
    enrollment_model = _enrollment_model()
    owner = youth_of(enrollment_id)
    if owner is None:
        return None
    if lock:
        youth_model = enrollment_model._meta.get_field("participant").related_model
        list(youth_model.objects.select_for_update().filter(pk=owner).values_list("pk"))
    rows = Placement.objects.filter(RUNNING, enrollment__participant_id=owner)
    if exclude is not None:
        rows = rows.exclude(pk=exclude)
    return rows.select_related("employer").first()


def _refuse_second(enrollment_id, *, exclude=None):
    if running := running_for_youth(enrollment_id, exclude=exclude, lock=True):
        raise ActivePlacementExists(running)


OPERATIONAL_STATUSES = {code for code, _ in Placement.OPERATIONAL_STATUSES}


def _self_employment(pathway: str, values: dict) -> dict:
    """The self-employment details (D-080 / B27, NEW-071), cleaned. They belong to the
    self-employment outcome only, so they are refused on any other pathway: a business is never
    counted as formal employment. All are optional ("income, where available")."""
    out = {
        "business_activity": (values.get("business_activity") or "").strip(),
        "operational_status": values.get("operational_status") or "",
        "business_evidence": (values.get("business_evidence") or "").strip(),
        "monthly_income": values.get("monthly_income"),
    }
    if pathway != Placement.SELF and any(v not in ("", None) for v in out.values()):
        raise PlacementError("Business details are recorded only for self-employment.")
    if out["operational_status"] and out["operational_status"] not in OPERATIONAL_STATUSES:
        raise PlacementError("Choose the business's operational status.")
    if out["monthly_income"] is not None and out["monthly_income"] < 0:
        raise PlacementError("Income cannot be negative.")
    return out


WORK_FIELDS = ("employment_type_id", "salary_amount", "salary_band_id")


def _band_holds(band: dict, amount) -> bool:
    low, high = band["min_amount"], band["max_amount"]
    return (low is None or amount >= Decimal(low)) and (high is None or amount <= Decimal(high))


def _work_terms(pathway: str, values: dict, existing: dict | None = None) -> dict:
    """Employment type, salary and band (B25, A3; PI360-NEW-035), cleaned. The self-employment
    type goes with the self-employment pathway only (B27). A salary is for paid work: a business
    records its income instead. An amount without a band takes the one band that holds it; an
    amount and a band that disagree are refused. ``existing`` holds the episode's current values,
    so a type or band retired since it was chosen is kept rather than refused."""
    existing = existing or {}
    out = {
        "employment_type_id": values.get("employment_type_id") or None,
        "salary_amount": values.get("salary_amount"),
        "salary_band_id": values.get("salary_band_id") or None,
    }

    def item(key, field, message):
        pk = out[field]
        if pk is None:
            return None
        same = str(pk) == str(existing.get(field) or "")
        row = configuration.outcome_item(key, pk, active_only=not same)
        if row is None:
            raise PlacementError(message)
        return row

    kind = item(
        "employment-types", "employment_type_id", "Choose an employment type from the list."
    )
    if kind and kind["self_employment"] != (pathway == Placement.SELF):
        raise PlacementError(
            "Self-employment is its own outcome: use the self-employment type with the "
            "self-employment pathway only."
        )
    amount = out["salary_amount"]
    if pathway == Placement.SELF and (amount is not None or out["salary_band_id"]):
        raise PlacementError("For self-employment, record the business income, not a salary.")
    if amount is not None and amount < 0:
        raise PlacementError("A salary cannot be negative.")
    band = item("salary-bands", "salary_band_id", "Choose a salary band from the list.")
    if amount is not None:
        if band is None:
            auto = configuration.salary_band_for(amount)
            out["salary_band_id"] = auto["id"] if auto else None
        elif not _band_holds(band, amount):
            raise PlacementError("The salary is outside the band chosen.")
    return out


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
    employment_type_id=None,
    salary_amount=None,
    salary_band_id=None,
    previous_placement_id=None,
    **business,
) -> Placement:
    """Append one placement episode. ``source_status`` is required: it is what was reported.
    ``previous_placement_id`` names the episode this one followed (a change of employer)."""
    if not source_status.strip():
        raise PlacementError("A placement needs the status as reported by the source.")
    if pathway and pathway not in PATHWAYS:
        raise PlacementError(f"Unknown pathway '{pathway}'.")
    _check_dates(start_date, end_date)
    unknown = set(business) - set(Placement.SELF_EMPLOYMENT_FIELDS)
    if unknown:
        raise TypeError(f"Unexpected fields: {', '.join(sorted(unknown))}")
    if not pathway and not status and (m := resolve_status(source_status)) and m.is_placement:
        pathway, status = m.pathway, m.status  # unmapped values stay blank: held for a steward
    if not _enrollment_model().objects.filter(pk=enrollment_id).exists():
        raise PlacementError("That enrollment does not exist.")
    work = _work_terms(
        pathway,
        {
            "employment_type_id": employment_type_id, "salary_amount": salary_amount,
            "salary_band_id": salary_band_id,
        },
    )  # fmt: skip
    if (
        previous_placement_id
        and not Placement.objects.filter(
            pk=previous_placement_id, enrollment__participant_id=youth_of(enrollment_id)
        ).exists()
    ):
        raise PlacementError("The earlier placement is not this youth's.")
    if status == PLACED and end_date is None:
        _refuse_second(enrollment_id)
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
        previous_placement_id=previous_placement_id,
        **work,
        **_self_employment(pathway, business),
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
    if is_current(placement) and before["status"] != PLACED:
        _refuse_second(placement.enrollment_id, exclude=placement.pk)
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

EDITABLE_BY_STAFF = (
    "employer_id", "employer_name_source", "designation", "start_date", "benefits",
    *Placement.SELF_EMPLOYMENT_FIELDS, *WORK_FIELDS,
)  # fmt: skip


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
    **business,
) -> Placement:
    """A placement a staff member observed and entered (a call, a visit). Always a real
    placement: the pathway is required and the status is 'placed'. ``business`` holds the
    self-employment details (NEW-071), allowed only on that pathway."""
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
        **business,
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
    business = {f: getattr(p, f) for f in Placement.SELF_EMPLOYMENT_FIELDS}
    given = {f: changes[f] for f in Placement.SELF_EMPLOYMENT_FIELDS if f in changes}
    business.update(given)
    _self_employment(p.pathway, given)  # refuses details given for another pathway
    if p.pathway != Placement.SELF:
        # Moving away from self-employment drops the business details; the audit "before"
        # snapshot keeps what they were (income only as recorded / not recorded).
        business = dict.fromkeys(Placement.SELF_EMPLOYMENT_FIELDS, "") | {"monthly_income": None}
    for field, value in _self_employment(p.pathway, business).items():
        setattr(p, field, value)
    existing = {f: getattr(p, f) for f in WORK_FIELDS}
    work = {**existing, **{f: changes[f] for f in WORK_FIELDS if f in changes}}
    if "salary_amount" in changes and "salary_band_id" not in changes:
        work["salary_band_id"] = None  # a new amount finds its band again
    if "pathway" in changes and "employment_type_id" not in changes and work["employment_type_id"]:
        kind = configuration.outcome_item(
            "employment-types", work["employment_type_id"], active_only=False
        )
        if kind and kind["self_employment"] != (p.pathway == Placement.SELF):
            work["employment_type_id"] = None  # the type went with the old pathway
    if p.pathway == Placement.SELF:
        work["salary_amount"], work["salary_band_id"] = None, None  # income is recorded instead
        if "salary_amount" in changes and changes["salary_amount"] is not None:
            raise PlacementError("For self-employment, record the business income, not a salary.")
    for field, value in _work_terms(p.pathway, work, existing).items():
        setattr(p, field, value)
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
def mark_recorded_twice(*, actor, placement_id, keep_id, reason: str) -> Placement:
    """NEW-077: two running rows describe the same real placement (found when two records of one
    youth are merged). An officer keeps one; the other is marked as recorded twice and points at
    it. Nothing is deleted or ended: the row, its dates and its author stay, and the audit trail
    keeps its earlier status. Only a person does this, never the system on its own."""
    if str(placement_id) == str(keep_id):
        raise PlacementError("Choose a different placement to keep.")
    if not (reason or "").strip():
        raise PlacementError("Give a reason.")
    rows = {str(r.pk): r for r in Placement.objects.select_for_update().filter(
        pk__in=[placement_id, keep_id]
    )}  # fmt: skip
    p, keep = rows.get(str(placement_id)), rows.get(str(keep_id))
    if p is None or keep is None:
        raise PlacementError("Placement not found.")
    if not (is_current(p) and is_current(keep)):
        raise PlacementError("Both placements must be running to be reconciled into one.")
    before = _snapshot(p)
    p.status, p.duplicate_of = Placement.RECORDED_TWICE, keep
    p.save(update_fields=sorted(Placement.REVIEWABLE))
    audit.record(
        actor=actor, action="placement.recorded_twice", object_type="placement", object_id=p.pk,
        before=before, after={**_snapshot(p), "kept": str(keep.pk)}, reason=reason.strip(),
    )  # fmt: skip
    return p


CHANGED_EMPLOYER = "Changed employer"


@transaction.atomic
def change_employer(
    *,
    actor,
    placement_id,
    end_date,
    start_date,
    pathway: str,
    employer_id=None,
    employer_name_source: str = "",
    designation: str = "",
    benefits: str = "",
    **business,
) -> Placement:
    """D-081: the youth left one job for another. Ends the running placement (reason "Changed
    employer") and records the new one, in one step: both happen or neither does."""
    old = Placement.objects.select_for_update().get(pk=placement_id)
    if not is_current(old):
        raise PlacementError("Only a running placement can be changed to a new employer.")
    if start_date is None:
        raise PlacementError("Give the date the new job started.")
    if end_date is not None and start_date < end_date:
        raise PlacementError("The new job cannot start before the old one ended.")
    end_episode(actor=actor, placement_id=old.pk, end_date=end_date, exit_reason=CHANGED_EMPLOYER)
    new = record_manual(
        actor=actor, enrollment_id=old.enrollment_id, pathway=pathway, start_date=start_date,
        employer_id=employer_id, employer_name_source=employer_name_source,
        designation=designation, benefits=benefits, previous_placement_id=old.pk, **business,
    )  # fmt: skip
    audit.record(
        actor=actor, action="placement.employer_changed", object_type="placement",
        object_id=new.pk, before={"ended": str(old.pk)}, after={"started": str(new.pk)},
    )  # fmt: skip
    return new


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
    blank fields are filled; a reviewed value is never changed. Returns how many were updated.
    A row that would become a youth's second running placement stays unmapped (held, D-081)."""
    n = held = 0
    for p in Placement.objects.filter(status="").select_for_update():
        m = resolve_status(p.source_status)
        if m is None or not m.is_placement:
            continue
        if m.status == PLACED and p.end_date is None:
            if running_for_youth(p.enrollment_id, exclude=p.pk, lock=True):
                held += 1
                continue
        p.status, p.pathway = m.status, p.pathway or m.pathway
        p.save(update_fields=sorted(Placement.REVIEWABLE))
        n += 1
    if n or held:
        audit.record(
            actor=actor, action="placement.mappings_applied", object_type="placement",
            object_id="bulk", after={"updated": n, "held_second_running": held},
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
    """Every placement mapped as a real placement: which enrollment, when it started, the pathway
    and the employer (``employer_id`` is None until a steward links the source name)."""
    return [
        {
            "id": i,
            "enrollment_id": e,
            "on": d or c.date(),
            "pathway": pw,
            "employer_id": emp,
            "employer_name": linked or source,
        }
        for i, e, d, c, pw, emp, linked, source in Placement.objects.filter(
            status="placed"
        ).values_list(
            "pk",
            "enrollment_id",
            "start_date",
            "created_at",
            "pathway",
            "employer_id",
            "employer__name",
            "employer_name_source",
        )
    ]


# ---- follow-up scheduling (T-066) -------------------------------------------------------------
# Imported last: followups.py imports names defined above, so this stays at the end of the file.
def outcome_list(key: str, *, include_inactive: bool = False) -> list[dict]:
    """The employment types, salary bands or reasons for leaving (NEW-034/035), for modules that
    may not read configuration themselves. ``key``: employment-types, salary-bands or
    leaving-reasons."""
    return configuration.outcome_list(key, include_inactive=include_inactive)


def outcome_name(key: str, pk) -> str:
    """The name of one entry, retired or not ('' when there is none)."""
    row = configuration.outcome_item(key, pk, active_only=False) if pk else None
    return row["name"] if row else ""


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
followup_facts = _followups.facts
followup_outcome_lists = _followups.outcome_lists
followup_unreachable = _followups.mark_unreachable
followup_update_step = _followups.update_step
generate_followups = _followups.generate_for


# --- exit feedback (NEW-039, NEW-076; D-079) -----------------------------------------------------


def with_exit_feedback(placement_ids) -> set:
    """Which of these episodes already have exit feedback."""
    return set(
        ExitFeedback.objects.filter(placement_id__in=placement_ids).values_list(
            "placement_id", flat=True
        )
    )


def exit_feedback_of(placement_id):
    return ExitFeedback.objects.filter(placement_id=placement_id).first()


@transaction.atomic
def record_exit_feedback(
    *, actor, placement_id, rating, comment="", assisted=True, confidential=True, given_on=None
) -> ExitFeedback:
    """One per ended episode. The comment and its text are never written to the audit trail."""
    p = Placement.objects.select_for_update().get(pk=placement_id)
    if p.end_date is None:
        raise PlacementError("Exit feedback can be recorded only after the placement has ended.")
    if ExitFeedback.objects.filter(placement=p).exists():
        raise PlacementError("Exit feedback has already been recorded for this placement.")
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        raise PlacementError("Give a rating from 1 to 5.")
    comment = (comment or "").strip()
    if len(comment) > 1000:
        raise PlacementError("Keep the comment to 1000 characters.")
    fb = ExitFeedback.objects.create(
        placement=p, rating=rating, comment=comment, assisted=assisted,
        confidential=confidential, given_on=given_on or timezone.localdate(), recorded_by=actor,
    )  # fmt: skip
    audit.record(
        actor=actor,
        action="placement.exit_feedback_recorded",
        object_type="placement",
        object_id=p.pk,
        after={"rating": rating, "assisted": assisted, "confidential": confidential,
               "has_comment": bool(comment)},
    )  # fmt: skip
    return fb
