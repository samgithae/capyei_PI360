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
    "enrollment_no": False,
    "gender": False,
    "age": False,
    "county_code": False,
    "phone": False,
    "email": False,
    "status": False,
    "source_id": False,
}
GENDERS = {"f": "female", "female": "female", "m": "male", "male": "male", "other": "other"}
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


def _text(raw, key):
    return str(raw.get(key, "") or "").strip()


def check_row(raw: dict) -> Checked:
    out = Checked()
    err = lambda f, m: out.errors.append({"field": f, "message": m})  # noqa: E731
    warn = lambda f, m: out.warnings.append({"field": f, "message": m})  # noqa: E731
    c = out.clean
    for f, required in FIELDS.items():
        c[f] = _text(raw, f)
        if required and not c[f]:
            err(f, "Required.")

    offering_id, prog_id, _inst, problems = configuration.resolve_offering(
        c["programme_code"], c["cohort_code"], c["course_code"]
    )
    for f, m in problems:
        err(f, m)

    county_id = None
    if c["county_code"]:
        county_id = configuration.county_id_by_code(c["county_code"])
        if county_id is None:
            warn("county_code", f"Unknown county '{c['county_code']}'; left blank.")
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
    if not (c["enrollment_no"] or c["source_id"]):
        warn("enrollment_no", "No enrollment number: cannot be matched on a re-import.")

    if prog_id and c["enrollment_no"]:
        out.source_key = f"{c['programme_code'].upper()}|{c['enrollment_no']}"
        if ParticipantEnrollment.objects.filter(
            programme_id=prog_id, source_enrollment_no=c["enrollment_no"]
        ).exists():
            out.match = "exact"
    c["_refs"] = {
        "offering": offering_id,
        "programme": prog_id,
        "county": county_id,
    }
    return out


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
    _o, _p, institution_id, _e = configuration.resolve_offering(
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
        cohort_course_id=refs["offering"],
        programme_id=refs["programme"],
        institution_id=institution_id,
        source_enrollment_no=clean["enrollment_no"],
        status=clean["status"],
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
