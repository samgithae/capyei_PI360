"""The CV of a youth: what an employer may see, built from the saved profile.

One function, :func:`build`, turns the stored records into a plain document that the screen and the
PDF both draw. It is the only place that decides what a CV contains, so the two cannot drift.

Never in a CV: National ID, date of birth, gender, programme or enrollment data, officer, status,
verification marks, scores, referrals or any internal id. Contact details are included only when
the caller may see them. Entries are ordered most recent first; a section with nothing in it is an
empty list (the screen and the PDF both leave it out)."""

import re
import unicodedata
from datetime import date

from .models import (
    EMPLOYMENT_TYPES,
    LANGUAGE_LEVELS,
    PRACTICAL_KINDS,
    WORK_PATTERNS,
    Participant,
    ParticipantReadiness,
    ParticipantSkill,
)

EMPLOYMENT_LABEL = dict(EMPLOYMENT_TYPES)
PRACTICAL_LABEL = dict(PRACTICAL_KINDS)
LANGUAGE_LABEL = dict(LANGUAGE_LEVELS)
PATTERN_LABEL = dict(WORK_PATTERNS)
SKILL_LABEL = dict(ParticipantSkill.PROFICIENCY)


def _name_parts(p: Participant) -> dict:
    """First, middle and last name as the registration stores them (given, family, other)."""
    parts = [p.given_name, p.family_name, p.other_names]
    if not any(x.strip() for x in parts):
        return {"first": "", "middle": "", "last": ""}
    return {
        "first": p.given_name.strip(),
        "middle": p.family_name.strip(),
        "last": p.other_names.strip(),
    }


def _full_name(p: Participant) -> str:
    parts = _name_parts(p)
    joined = " ".join(x for x in parts.values() if x)
    return joined or p.full_name_source.strip()


def _contact(p: Participant, kind: str) -> str:
    rows = [c for c in p.contacts.all() if c.kind == kind]
    rows.sort(key=lambda c: not c.is_primary)
    return rows[0].value if rows else ""


def _period(start, end, current) -> str:
    """'Jan 2022 - Present'."""
    if start is None and end is None:
        return "Present" if current else ""
    left = start.strftime("%b %Y") if start else ""
    right = "Present" if current else (end.strftime("%b %Y") if end else "")
    if left and right:
        return f"{left} - {right}"
    return left or right


def _duration(months: int) -> str:
    years, rest = divmod(months, 12)
    bits = []
    if years:
        bits.append(f"{years} yr" + ("s" if years > 1 else ""))
    if rest:
        bits.append(f"{rest} mo")
    return " ".join(bits)


_FAR = date(1900, 1, 1)


def _years(q) -> str:
    end = "Present" if q.currently_studying else (str(q.year_awarded) if q.year_awarded else "")
    start = str(q.start_year) if q.start_year else ""
    return " - ".join(x for x in (start, end) if x)


def _education(rows) -> list:
    rows = sorted(
        rows,
        key=lambda q: (q.currently_studying, q.year_awarded or 0, q.start_year or 0),
        reverse=True,
    )
    out = []
    for q in rows:
        out.append(
            {
                "level": q.level.name,
                "course": q.title,
                "institution": q.institution,
                "field_of_study": q.field_of_study,
                "grade": q.grade.name if q.grade_id else "",
                "period": _years(q),
                "currently_studying": q.currently_studying,
            }
        )
    return out


def _experience(rows) -> list:
    rows = sorted(
        rows,
        key=lambda e: (e.is_current, e.end_date or _FAR, e.start_date or _FAR, e.months),
        reverse=True,
    )
    return [
        {
            "title": e.role_title,
            "employer": e.employer_name,
            "employment_type": EMPLOYMENT_LABEL.get(e.employment_type, ""),
            "period": _period(e.start_date, e.end_date, e.is_current),
            "duration": _duration(e.months),
            "responsibilities": e.responsibilities,
            "achievements": e.achievements,
        }
        for e in rows
    ]


def _practical(rows) -> list:
    rows = sorted(rows, key=lambda x: (x.end_date or date.max, x.start_date or _FAR), reverse=True)
    return [
        {
            "organisation": x.organisation,
            "role": x.role,
            "kind": PRACTICAL_LABEL.get(x.kind, x.kind),
            "period": _period(x.start_date, x.end_date, False),
            "description": x.description,
        }
        for x in rows
    ]


def _certifications(rows) -> list:
    rows = sorted(rows, key=lambda c: (c.year_obtained or 0, c.name), reverse=True)
    return [
        {
            "name": c.name,
            "issuer": c.issuer,
            "year": c.year_obtained,
            "expiry": c.expiry_date.strftime("%b %Y") if c.expiry_date else "",
        }
        for c in rows
    ]


def completeness(
    *, contact: bool, summary: bool, education: bool, skills: bool, extras: dict
) -> dict:
    """Share of the four essentials that are filled in. Not related to placement readiness, and
    having no work experience never lowers it."""
    checks = [
        (
            "contact",
            "Contact details",
            contact,
            "Add a phone number or email so employers can reach you.",
        ),
        ("summary", "Professional summary", summary, "Write two to four sentences about yourself."),
        ("education", "Education", education, "Add at least one education record."),
        ("skills", "Skills", skills, "Pick the skills you can show an employer."),
    ]
    done = sum(1 for _, _, ok, _ in checks if ok)
    return {
        "percent": round(100 * done / len(checks)),
        "missing": [
            {"key": k, "label": label, "hint": hint} for k, label, ok, hint in checks if not ok
        ],
        # Worth adding, but they do not count towards the percentage.
        "suggestions": [s for s, shown in extras.items() if shown],
    }


def build(p: Participant, *, include_contact: bool = True, has_photo: bool = False) -> dict:
    """The CV document. ``include_contact`` is False for a caller without contact permission."""
    res = p.residences.filter(valid_to__isnull=True).select_related("county").first()
    county = (
        res.county.name
        if res and res.county_id
        else (p.origin_county.name if p.origin_county_id else "")
    )
    sub_county = res.sub_county_source.strip() if res else ""
    phone = _contact(p, "phone") if include_contact else ""
    email = _contact(p, "email") if include_contact else ""

    ready = ParticipantReadiness.objects.filter(participant=p).first()
    skills = list(p.skills.select_related("skill"))
    exp = list(p.experience.all())
    quals = list(p.qualifications.select_related("level", "grade"))
    certs = list(p.certifications.all())
    practical = list(p.practical_experience.all())
    languages = list(p.languages.all())
    no_experience = bool(ready and ready.no_work_experience and not exp)

    summary = ready.summary.strip() if ready else ""
    prefs = {
        "roles": list(ready.preferred_roles) if ready else [],
        "sectors": [s.name for s in ready.interest_sectors.order_by("name")] if ready else [],
        "counties": [c.name for c in ready.preferred_counties.order_by("name")] if ready else [],
        "work_patterns": [PATTERN_LABEL.get(c, c) for c in (ready.work_patterns if ready else [])],
        "available_from": ready.available_from.strftime("%d %b %Y")
        if ready and ready.available_from
        else "",
        "willing_to_relocate": ready.willing_to_relocate if ready else None,
    }
    has_prefs = any(
        [
            prefs["roles"],
            prefs["sectors"],
            prefs["counties"],
            prefs["work_patterns"],
            prefs["available_from"],
        ]
        or [prefs["willing_to_relocate"] is not None]
    )

    return {
        "name": _full_name(p),
        "name_parts": _name_parts(p),
        "headline": prefs["roles"][0] if prefs["roles"] else "",
        "has_photo": has_photo,
        "contact": {
            "phone": phone,
            "email": email,
            "location": ", ".join(x for x in (sub_county, county) if x),
            "county": county,
            "sub_county": sub_county,
        },
        "summary": summary,
        "education": _education(quals),
        "experience": _experience(exp),
        "no_work_experience": no_experience,
        "practical": _practical(practical),
        "skills": [
            {"name": s.skill.name, "level": SKILL_LABEL.get(s.proficiency, "")}
            for s in sorted(skills, key=lambda s: (-s.proficiency, s.skill.name))
        ],
        "certifications": _certifications(certs),
        "languages": [
            {"language": x.language, "level": LANGUAGE_LABEL.get(x.proficiency, "")}
            for x in languages
        ],
        "preferences": prefs if has_prefs else None,
        "completeness": completeness(
            contact=bool(phone or email) if include_contact else _has_contact(p),
            summary=bool(summary),
            education=bool(quals),
            skills=bool(skills),
            extras={
                "photo": not has_photo,
                "experience": not exp and not no_experience and not practical,
                "languages": not languages,
                "certifications": not certs,
                "preferences": not has_prefs,
            },
        ),
    }


def _has_contact(p: Participant) -> bool:
    return any(c.value for c in p.contacts.all())


def filename(name: str) -> str:
    """``Samuel_Kamau_CV.pdf``: ASCII only, safe in a header and on any file system."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = re.sub(r"[^A-Za-z0-9]+", " ", ascii_name).split()
    return "_".join(words + ["CV"]) + ".pdf" if words else "CV.pdf"
