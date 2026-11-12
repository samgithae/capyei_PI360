"""Bulk-load capability facts (qualifications, skills, experience, availability) from a file.

One row per fact. Youth are found by their source enrollment number (add a programme code when
the same number is used in more than one programme) and only if the user may see them. Facts are
recorded as source "import", unverified. Add-only and safe to run twice: a fact the youth already
has is skipped, never changed. A dry run does everything except keep the result."""

import csv
import io
import re
from datetime import date

from django.db import transaction

from apps.audit import services as audit
from apps.configuration import services as configuration

from .models import (
    WORK_PATTERNS,
    Participant,
    ParticipantEnrollment,
    ParticipantExperience,
    ParticipantQualification,
    ParticipantReadiness,
    ParticipantSkill,
    ProfileFact,
)

ERROR_CAP = 200
HEADER = ["enrollment_no", "programme", "type", "value", "detail", "months", "year", "grade"]
ALIASES = {
    "enrollment_no": ("enrollment no", "enrolment no", "enrollment number", "enrollment"),
    "programme": ("programme code",),
    "type": ("kind", "fact"),
    "value": ("item", "name"),
    "detail": ("extra", "notes"),
    "months": ("months of experience",),
    "year": ("year awarded",),
    "grade": ("result", "class"),
}
EXAMPLES = [
    [
        "E-0001",
        "P01",
        "qualification",
        "Diploma",
        "Diploma in Food Production",
        "",
        "2023",
        "Credit",
    ],
    ["E-0001", "P01", "skill", "Customer service", "advanced", "", "", ""],
    ["E-0001", "P01", "experience", "Waiter", "Example Hotel", "18", "", ""],
    ["E-0001", "P01", "availability", "2026-12-01", "full_time; part_time", "", "", ""],
]
LEVELS = {"basic": 1, "working": 2, "advanced": 3, "1": 1, "2": 2, "3": 3}
PATTERNS = {c: c for c, _ in WORK_PATTERNS} | {n.lower(): c for c, n in WORK_PATTERNS}


class RowError(Exception):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


def template_csv() -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(HEADER)
    w.writerows(EXAMPLES)
    return out.getvalue()


def norm(text):
    return " ".join("".join(c if c.isalnum() else " " for c in text.casefold()).split())


def _columns(header):
    seen = {norm(h): i for i, h in enumerate(header) if h}
    cols = {}
    for field in HEADER:
        for spelling in (field.replace("_", " "), *ALIASES.get(field, ())):
            if norm(spelling) in seen:
                cols[field] = seen[norm(spelling)]
                break
    missing = [f for f in ("enrollment_no", "type", "value") if f not in cols]
    if missing:
        raise configuration.ConfigError(
            "file", "Missing column(s): " + ", ".join(m.replace("_", " ") for m in missing) + "."
        )
    return cols


def _date(raw):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw) or re.match(
        r"^(\d{1,2})/(\d{1,2})/(\d{4})$", raw
    )
    if m:
        a, b, c = (int(x) for x in m.groups())
        try:
            return date(a, b, c) if len(m.group(1)) == 4 else date(c, b, a)
        except ValueError:
            pass
    raise RowError("value", "Availability must be a date such as 2026-12-01.")


def _whole(raw, field, low, high):
    try:
        n = int(float(raw))
    except ValueError:
        raise RowError(field, f"{field} must be a whole number.") from None
    if not low <= n <= high:
        raise RowError(field, f"{field} must be between {low} and {high}.")
    return n


def _participant(user, row, cache):
    number = row["enrollment_no"]
    if not number:
        raise RowError("enrollment_no", "Enrollment number is required.")
    programme = row.get("programme", "")
    key = (number.casefold(), programme.casefold())
    if key not in cache:
        qs = ParticipantEnrollment.objects.filter(
            source_enrollment_no__iexact=number,
            participant__in=Participant.objects.visible_to(user).values("pk"),
        )
        if programme:
            qs = qs.filter(programme__code__iexact=programme)
        ids = set(qs.values_list("participant_id", flat=True)[:2])
        cache[key] = ids
    ids = cache[key]
    if not ids:
        raise RowError("enrollment_no", f"No youth you can see has enrollment number '{number}'.")
    if len(ids) > 1:
        raise RowError(
            "enrollment_no", f"'{number}' matches more than one youth; add the programme."
        )
    return Participant.objects.get(pk=next(iter(ids)))


def _stamp(obj, actor):
    obj.source, obj.entered_by = ProfileFact.IMPORT, actor
    obj.verified_by, obj.verified_at = None, None


def _apply(actor, p, row):
    """Add one fact. Returns (kind, outcome) where outcome is 'added' or 'skipped'."""
    kind = row["type"].strip().lower()
    value, detail = row["value"].strip(), row.get("detail", "").strip()
    if not value:
        raise RowError("value", "Value is required.")
    if kind == "qualification":
        level, problem = configuration.find_active_reference("qualification-levels", value)
        if problem:
            raise RowError("value", f"Qualification level '{value}': {problem}.")
        year = _whole(row["year"], "year", 1950, 2100) if row.get("year") else None
        qs = ParticipantQualification.objects.filter(participant=p, level=level, title=detail)
        if qs.exists():
            return kind, "skipped"
        obj = ParticipantQualification(
            participant=p,
            level=level,
            title=detail[:200],
            year_awarded=year,
            grade=row.get("grade", "")[:60],
        )
    elif kind == "skill":
        skill, problem = configuration.find_active_reference("skills", value)
        if problem:
            raise RowError("value", f"Skill '{value}': {problem}.")
        level = LEVELS.get(detail.lower(), None) if detail else ParticipantSkill.WORKING
        if level is None:
            raise RowError("detail", "Skill level must be basic, working or advanced.")
        if ParticipantSkill.objects.filter(participant=p, skill=skill).exists():
            return kind, "skipped"
        obj = ParticipantSkill(participant=p, skill=skill, proficiency=level)
    elif kind == "experience":
        if not row.get("months"):
            raise RowError("months", "Months of experience is required.")
        months = _whole(row["months"], "months", 0, 720)
        if ParticipantExperience.objects.filter(
            participant=p, role_title__iexact=value, employer_name__iexact=detail, months=months
        ).exists():
            return kind, "skipped"
        obj = ParticipantExperience(
            participant=p, role_title=value[:200], employer_name=detail[:200], months=months
        )
    elif kind == "availability":
        when = _date(value)
        patterns = []
        for part in re.split(r"[;,|]", detail):
            part = part.strip().lower().replace(" ", "_")
            if not part:
                continue
            if part not in PATTERNS:
                raise RowError("detail", f"Unknown work pattern '{part}'.")
            patterns.append(PATTERNS[part])
        existing = ParticipantReadiness.objects.filter(participant=p).first()
        if existing and existing.available_from:
            return kind, "skipped"
        obj = existing or ParticipantReadiness(participant=p)
        obj.available_from = when
        if patterns and not obj.work_patterns:
            obj.work_patterns = sorted(set(patterns))
    else:
        raise RowError("type", "Type must be qualification, skill, experience or availability.")
    _stamp(obj, actor)
    obj.save()
    return kind, "added"


def run_import(*, actor, filename, content, dry_run):
    table = configuration.read_upload(filename, content)
    cols = _columns(table[0][1])
    added = {}
    skipped = 0
    errors = []
    touched = set()
    cache = {}
    with transaction.atomic():
        for number, cells in table[1:]:
            row = {f: (cells[i] if i < len(cells) else "") for f, i in cols.items()}
            try:
                with transaction.atomic():
                    p = _participant(actor, row, cache)
                    kind, outcome = _apply(actor, p, row)
            except RowError as exc:
                errors.append({"row": number, "field": exc.field, "message": str(exc)})
                continue
            if outcome == "added":
                added[kind] = added.get(kind, 0) + 1
                touched.add(p.pk)
            else:
                skipped += 1
        if not dry_run and added:
            audit.record(
                actor=actor,
                action="participant.profile_imported",
                object_type="participant",
                object_id=None,
                after={"added": added, "youth": len(touched), "source": ProfileFact.IMPORT},
            )
        if dry_run:
            transaction.set_rollback(True)
    return {
        "dry_run": dry_run,
        "rows": len(table) - 1,
        "added": added,
        "added_total": sum(added.values()),
        "youth": len(touched),
        "skipped": skipped,
        "failed": len(errors),
        "errors": errors[:ERROR_CAP],
    }
