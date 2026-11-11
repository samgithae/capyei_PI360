"""Public interface of apps.participants.

``import_participant`` is what the import pipeline calls (T-040): it validates one normalised row
against reference data and, when asked, creates or updates the participant and enrolment. The
pipeline never touches participant models itself.
"""

from dataclasses import dataclass, field

from django.db import transaction

from apps.configuration import services as configuration

from .models import Participant, ParticipantContact, ParticipantEnrollment, SourceIdentifier

# Field -> required? The mapping templates target exactly these names.
FIELDS = {
    "full_name": True,
    "programme_code": True,
    "cohort_code": True,
    "course_code": True,
    "enrollment_no": True,  # D-050: blocks with the name; match key for D-059
    "gender": False,
    "age": False,
    "county_code": False,
    "phone": False,
    "email": False,
    "status": False,
    "source_id": False,
}
EXTRA = "extra:"  # a mapping target: keep this column under its own label
MAX_EXTRA_LABEL, MAX_EXTRA_VALUE = 60, 500


def is_target(name: str) -> bool:
    """A valid mapping target: a core field, or ``extra:<label>`` for any other column."""
    return name in FIELDS or (
        name.startswith(EXTRA) and 0 < len(name[len(EXTRA) :].strip()) <= MAX_EXTRA_LABEL
    )


GENDERS = {"f": "female", "female": "female", "m": "male", "male": "male", "other": "other"}
IMPORT_RULES = [
    "A row is held (not loaded) if full name or enrollment number is missing (D-050), or if "
    "programme, cohort or course is missing or not in the reference data (an enrollment cannot "
    "exist without them).",
    "A row matches an existing record on programme + enrollment number; matched rows are "
    "skipped, never updated (D-059: imports add new people only).",
    "Unknown county, gender or age become blank/unknown with a warning; they never block a row.",
    "Rows already loaded from an earlier file (same key and content) are skipped.",
    "Possible duplicates found after a load are queued for a steward and are never merged "
    "automatically.",
]  # Rules are proposals until D-004/D-005 are settled.
STATUSES = {"active": "enrolled", "enrolled": "enrolled", "completed": "completed",
            "withdrawn": "withdrawn"}  # fmt: skip


@dataclass
class Checked:
    """Result of checking one row. ``errors`` block the row; ``warnings`` do not."""

    clean: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)  # [{"field", "message"}]
    warnings: list = field(default_factory=list)
    source_key: str = ""
    match: str = "new"  # new | exact (same programme + enrollment number already loaded)
    diff: list = field(default_factory=list)  # [{"field","current","incoming"}] for exact matches


def _text(raw, key):
    return str(raw.get(key, "") or "").strip()


def check_row(raw: dict) -> Checked:
    out = Checked()
    err = lambda f, m: out.errors.append({"field": f, "message": m})  # noqa: E731
    warn = lambda f, m: out.warnings.append({"field": f, "message": m})  # noqa: E731
    c = out.clean
    c["extra"] = {
        k[len(EXTRA) :].strip(): _text(raw, k)[:MAX_EXTRA_VALUE]
        for k in raw
        if k.startswith(EXTRA) and _text(raw, k)
    }
    for f, required in FIELDS.items():
        c[f] = _text(raw, f)
        if required and not c[f]:
            err(f, "Required.")

    offering_id, prog_id, _inst, problems = configuration.resolve_offering(
        c["programme_code"], c["cohort_code"], c["course_code"]
    )
    county_id = None
    if c["county_code"]:
        county_id = configuration.county_id_by_code(c["county_code"])
        if county_id is None:
            warn("county_code", f"Unknown county '{c['county_code']}'; left blank.")
    fixable = {"cohort_code", "course_code"}
    if problems and {f for f, _m in problems} <= fixable:
        # The centre, cohort or course is just not in reference data yet: propose creating it
        # instead of blocking. Nothing is created until the batch is approved.
        proposal = configuration.propose_reference(
            c["programme_code"], c["cohort_code"], c["course_code"], county_id
        )
        if proposal:
            problems = []
            c["_proposed"] = proposal
            made = ", ".join(f"{i['kind'][:-1].replace('-', ' ')} {i['label']}" for i in proposal)
            warn("cohort_code", f"New reference data will be created on approval: {made}.")
    for f, m in problems:
        err(f, m)
    if c["phone"]:  # spec 15 §4: a warning, never a rewrite (rule N-03 is a proposal)
        digits = sum(ch.isdigit() for ch in c["phone"])
        if digits == 9:
            warn("phone", "Phone has 9 digits; a leading 0 may be missing. Stored as received.")
        elif digits != 10:
            warn("phone", f"Phone has {digits} digits; 10 expected. Stored as received.")
    if c["gender"]:
        g = GENDERS.get(c["gender"].lower())
        if g is None:
            warn("gender", f"Unrecognised gender '{c['gender']}'; stored as unknown.")
        c["gender"] = g or "unknown"
    else:
        c["gender"] = "unknown"
    if c["age"]:
        try:
            age = int(float(c["age"]))
            if not 10 <= age <= 100:
                raise ValueError
            c["age"] = age
        except ValueError:
            warn("age", f"Age '{c['age']}' is not usable; left blank.")
            c["age"] = None
    else:
        c["age"] = None
    c["status"] = STATUSES.get(c["status"].lower(), "unknown")

    if prog_id and c["enrollment_no"]:
        out.source_key = f"{c['programme_code'].upper()}|{c['enrollment_no']}"
        existing = (
            ParticipantEnrollment.objects.select_related("participant__origin_county")
            .filter(programme_id=prog_id, source_enrollment_no=c["enrollment_no"])
            .first()
        )
        if existing:
            out.match = "exact"
            out.diff = _diff(existing, c)
    c["_refs"] = {
        "offering": offering_id,
        "programme": prog_id,
        "county": county_id,
    }
    return out


def _diff(e: ParticipantEnrollment, c: dict) -> list:
    """Field-by-field differences between the stored person and the file row (spec 15 §5).

    Read-only: D-059 means imports never update, so this is information for the steward. A field
    is compared only when the file actually supplies a usable value, so blanks and "unknown"
    never show as differences."""
    p = e.participant
    phone = p.contacts.filter(kind="phone").values_list("value", flat=True).first() or ""
    email = p.contacts.filter(kind="email").values_list("value", flat=True).first() or ""
    pairs = [
        ("full_name", p.full_name_source, c["full_name"]),
        ("gender", p.gender, c["gender"] if c["gender"] != "unknown" else None),
        ("age", p.age_at_source, c["age"]),
        ("status", e.status, c["status"] if c["status"] != "unknown" else None),
        ("county_code", p.origin_county.code if p.origin_county else "", c["county_code"] or None),
        ("phone", phone, c["phone"] or None),
        ("email", email, c["email"] or None),
    ]
    return [
        {"field": f, "current": "" if cur is None else str(cur), "incoming": str(new)}
        for f, cur, new in pairs
        if new is not None
        and str(cur if cur is not None else "").strip().lower() != str(new).strip().lower()
    ]


def _snapshot(p: Participant, e: ParticipantEnrollment) -> dict:
    return {
        "full_name": p.full_name_source,
        "gender": p.gender,
        "age": p.age_at_source,
        "status": e.status,
        "county": str(p.origin_county_id or ""),
    }


@transaction.atomic
def import_participant(clean: dict, *, batch_ref: str) -> tuple[str, str, dict, dict]:
    """Create or update. Returns (action, participant_id, before, after).

    Matching is deterministic: programme + enrollment number. The rule for fields an officer has
    corrected since the last import (R-15, D-005) is not built yet, so updates overwrite.
    """
    refs = clean["_refs"]
    offering_id, _p, institution_id, _e = configuration.resolve_offering(
        clean["programme_code"], clean["cohort_code"], clean["course_code"]
    )
    existing = None
    if clean["enrollment_no"]:
        existing = (
            ParticipantEnrollment.objects.select_related("participant")
            .filter(programme_id=refs["programme"], source_enrollment_no=clean["enrollment_no"])
            .first()
        )
    if existing:
        p, e = existing.participant, existing
        before = _snapshot(p, e)
        p.full_name_source = clean["full_name"]
        if clean["gender"] != "unknown":
            p.gender = clean["gender"]
        if clean["age"] is not None:
            p.age_at_source = clean["age"]
        if refs["county"]:
            p.origin_county_id = refs["county"]
        p.save()
        if clean["status"] != "unknown":
            e.status = clean["status"]
            e.save()
        return "update", str(p.pk), before, _snapshot(p, e)

    p = Participant.objects.create(
        full_name_source=clean["full_name"],
        gender=clean["gender"],
        age_at_source=clean["age"],
        origin_county_id=refs["county"],
    )
    e = ParticipantEnrollment.objects.create(
        participant=p,
        cohort_course_id=offering_id or refs["offering"],
        programme_id=refs["programme"],
        institution_id=institution_id,
        source_enrollment_no=clean["enrollment_no"],
        status=clean["status"],
        extra=clean.get("extra") or {},
    )
    if clean["phone"]:
        ParticipantContact.objects.create(
            participant=p, kind="phone", value=clean["phone"], is_primary=True
        )
    if clean["email"]:
        ParticipantContact.objects.create(
            participant=p, kind="email", value=clean["email"], is_primary=True
        )
    if clean["source_id"]:
        SourceIdentifier.objects.create(
            participant=p, source=f"import:{batch_ref[:8]}", identifier=clean["source_id"]
        )
    return "create", str(p.pk), {}, _snapshot(p, e)


@transaction.atomic
def undo_import(*, action: str, participant_id: str, before: dict) -> None:
    """Reverse one lineage entry: delete what an import created, restore what it changed."""
    p = Participant.objects.filter(pk=participant_id).first()
    if p is None:
        return
    if action == "create":
        p.delete()  # enrollments, contacts and identifiers cascade
        return
    p.full_name_source = before["full_name"]
    p.gender = before["gender"]
    p.age_at_source = before["age"]
    p.origin_county_id = before["county"] or None
    p.save()
    e = p.enrollments.first()
    if e:
        e.status = before["status"]
        e.save()


# Duplicate detection and merge (T-041) live in duplicates.py; other modules import them from here.
from .duplicates import (  # noqa: E402
    DuplicateFailure,
    cohort_counts,
    dismiss,
    find_pairs,
    involved_in_merge,
    merge,
    quarantined,
    scan,
    unmerge,
)

__all__ = [
    "DuplicateFailure",
    "cohort_counts",
    "dismiss",
    "find_pairs",
    "involved_in_merge",
    "merge",
    "quarantined",
    "scan",
    "unmerge",
]


def create_proposed_reference(*, actor, items):
    """Create the centres, courses, cohorts and offerings an import proposed (see check_row)."""
    try:
        return configuration.create_proposed(actor=actor, items=items)
    except configuration.ConfigError as exc:
        raise ValueError(exc.message) from exc


def offering_resolves(clean: dict) -> list:
    """Problems (``[(field, message)]``) still stopping this row's cohort/course resolving."""
    return configuration.resolve_offering(
        clean["programme_code"], clean["cohort_code"], clean["course_code"]
    )[3]


def reference_codes():
    """Programme, cohort and course codes people can type or pick when importing."""
    return configuration.reference_codes()


def find_enrollment(programme_code, enrollment_no):
    """Id of the enrollment with this programme code and source enrollment number, or None.
    Lets other modules (the placement import) attach records without touching our models."""
    code, no = (programme_code or "").strip(), (enrollment_no or "").strip()
    if not code or not no:
        return None
    pk = (
        ParticipantEnrollment.objects.filter(programme__code__iexact=code, source_enrollment_no=no)
        .values_list("pk", flat=True)
        .first()
    )
    return str(pk) if pk else None


def extra_labels(programme_code):
    """The ``extra`` labels held on enrollments of one programme, with how many have a value.
    Also counts enrollments with no source enrollment number (they cannot be matched later)."""
    labels: dict[str, int] = {}
    qs = ParticipantEnrollment.objects.filter(
        programme__code__iexact=(programme_code or "").strip()
    )
    total = no_number = 0
    for no, extra in qs.values_list("source_enrollment_no", "extra").iterator():
        total += 1
        no_number += not no
        for k, v in (extra or {}).items():
            if str(v).strip():
                labels[k] = labels.get(k, 0) + 1
    return {
        "enrollments": total,
        "without_number": no_number,
        "labels": [{"label": k, "filled": n} for k, n in sorted(labels.items())],
    }


def extra_rows(programme_code, labels):
    """(source enrollment number, {label: value}) for enrollments that have a number and at least
    one of ``labels`` filled. Read-only; the caller turns these into an import file."""
    qs = (
        ParticipantEnrollment.objects.filter(programme__code__iexact=(programme_code or "").strip())
        .exclude(source_enrollment_no="")
        .order_by("source_enrollment_no")
    )
    for no, extra in qs.values_list("source_enrollment_no", "extra").iterator():
        got = {k: str(extra[k]).strip() for k in labels if str((extra or {}).get(k, "")).strip()}
        if got:
            yield no, got
