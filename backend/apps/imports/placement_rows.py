"""Placement import profile (T-087 stage D): template target ``placements``.

A file row says "this trainee (programme + enrollment number) had this outcome with this
organisation". Rows for people not already on file are held (doc 21 §5.6). A status value that no
steward has mapped holds the row (D-061). The organisation text is kept as reported; it becomes an
employer link only through a steward's cluster decision, made before or after loading (ADR-020:
history is added, never overwritten)."""

import re
from datetime import datetime

from apps.employers import services as employers
from apps.participants import services as participants
from apps.placements import services as placements

# Field -> required?
FIELDS = {
    "programme_code": True,
    "enrollment_no": True,
    "placement_status": True,
    "organisation": False,
    "address": False,
    "designation": False,
    "placement_date": False,
    "benefits": False,
    "contact_name": False,
    "contact_phone": False,
    "contact_email": False,
}
DEFAULTABLE = ("programme_code",)
SYNONYMS = {
    "programme": "programme_code", "program": "programme_code", "enrollmentno": "enrollment_no",
    "enrollmentnumber": "enrollment_no", "enrolmentno": "enrollment_no",
    "status": "placement_status", "organization": "organisation", "employer": "organisation",
    "orgphysicaladdress": "address", "organisationaddress": "address",
    "contactperson": "contact_name", "contactpersonphone": "contact_phone",
    "contactpersonemail": "contact_email", "date": "placement_date",
}  # fmt: skip
IMPORT_RULES = [
    "A row is held if the enrollment number is not already on file: a placement import adds "
    "nothing for people who have not been loaded.",
    "A row is held if the placement status is blank or has not been mapped to a meaning yet. "
    "Map the value, then re-check the batch.",
    "A status mapped as a referral outcome (for example an offer declined) is skipped, not "
    "loaded as a placement.",
    "Each row adds a new placement; earlier placements of the same person are never changed.",
    "The organisation is kept as written. It is linked to an employer only when a steward "
    "decides its name group.",
    "An unreadable date warns and the placement is kept without a date.",
]
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y")


def is_target(name: str) -> bool:
    return name in FIELDS


def _text(raw, key):
    return str(raw.get(key, "") or "").strip()


def parse_date(text):
    """A date from the formats seen in files (including Excel's 'YYYY-MM-DD 00:00:00'), or None."""
    s = re.sub(r"\s+00:00:00$", "", text.strip())
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def check_row(raw: dict) -> participants.Checked:
    out = participants.Checked()
    c = out.clean
    for f, required in FIELDS.items():
        c[f] = _text(raw, f)
        if required and not c[f]:
            out.errors.append({"field": f, "message": "Required."})
    if c["programme_code"] and c["enrollment_no"]:
        out.source_key = f"{c['programme_code'].upper()}|{c['enrollment_no']}"
        eid = participants.find_enrollment(c["programme_code"], c["enrollment_no"])
        if eid is None:
            out.errors.append(
                {
                    "field": "enrollment_no",
                    "message": "No enrollment with this number is on file; load the people first.",
                }
            )
        c["_refs"] = {"enrollment": eid}
    if c["placement_status"]:
        mapping = placements.resolve_status(c["placement_status"])
        if mapping is None:
            out.errors.append(
                {
                    "field": "placement_status",
                    "message": f"Status '{c['placement_status']}' is not mapped to a meaning yet.",
                }
            )
        elif not mapping.is_placement:
            c["_skip"] = True
            out.warnings.append(
                {
                    "field": "placement_status",
                    "message": "A referral outcome, not a placement; skipped.",
                }
            )
    if c["placement_date"]:
        d = parse_date(c["placement_date"])
        if d is None:
            out.warnings.append(
                {
                    "field": "placement_date",
                    "message": f"Date '{c['placement_date']}' is unreadable; kept without a date.",
                }
            )
        c["date"] = d.isoformat() if d else None
    else:
        c["date"] = None
    if c["contact_email"] and "@" not in c["contact_email"]:
        out.warnings.append(
            {"field": "contact_email", "message": "Email looks invalid; stored as received."}
        )
    return out


def commit_row(clean: dict, *, actor, row_id: int):
    """Add one placement. Returns (placement_id, before, after); ``before`` holds what to undo."""
    org = clean["organisation"]
    employer_id = employers.resolve_name(org) if org else None
    p = placements.record(
        actor=actor,
        enrollment_id=clean["_refs"]["enrollment"],
        source_status=clean["placement_status"],
        employer_name_source=org,
        designation=clean["designation"],
        start_date=datetime.fromisoformat(clean["date"]).date() if clean["date"] else None,
        benefits=clean["benefits"],
        employer_id=employer_id,
        source_row_id=row_id,
    )
    undo = {}
    if employer_id:
        undo = employers.enrich_from_import(
            actor=actor, employer_id=employer_id, address=clean["address"],
            contact_name=clean["contact_name"], phone=clean["contact_phone"],
            email=clean["contact_email"],
        )  # fmt: skip
    before = {"employer": str(employer_id), "undo": undo} if undo else {}
    return str(p.pk), before, {"employer": str(employer_id or ""), "status": p.status}


def undo_rows(*, actor, entries):
    """Reverse a batch's lineage entries: remove the placements, then what they added."""
    placements.undo_import(actor=actor, placement_ids=[e.record_id for e in entries])
    for e in entries:
        if e.before.get("undo"):
            employers.undo_enrichment(employer_id=e.before["employer"], undone=e.before["undo"])
