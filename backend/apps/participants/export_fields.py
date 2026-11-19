"""The fields a youth export can hold, grouped by where they come from.

One row is one youth. Related records (enrolments, qualifications, work experience, skills and so
on) are joined into a single cell, separated by "; ", so the file stays one row per youth.

Contact, date of birth and address fields are marked ``sensitive``: they are offered like any other
field, but the screen shows them with a warning. Not offered: staff notes, verification notes,
free-text duties and achievements, photos, and a national ID number (the system does not store one).
The rows come from the same filter as the youth table, so scope and filters always match."""

from collections.abc import Callable
from dataclasses import dataclass

from django.utils import timezone

from .models import WORK_PATTERNS, Participant

SEP = "; "
PATTERN = dict(WORK_PATTERNS)


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    get: Callable[[Participant], object]
    prefetch: tuple[str, ...] = ()
    select: tuple[str, ...] = ()
    sensitive: bool = False


def _join(items) -> str:
    return SEP.join(str(i) for i in items if i not in (None, ""))


def _date(d) -> str:
    return d.isoformat() if d else ""


def _yes_no(v) -> str:
    return "" if v is None else "Yes" if v else "No"


def _enrolments(p):
    return sorted(p.enrollments.all(), key=lambda e: (e.created_at, e.pk))


def _residence(p):
    return next((r for r in p.residences.all() if r.valid_to is None), None)


def _readiness(p):
    return getattr(p, "readiness", None)


def _patterns(p) -> str:
    r = _readiness(p)
    return _join(PATTERN.get(c, c) for c in (r.work_patterns if r else []))


def _contacts(p, kind):
    rows = [c for c in p.contacts.all() if c.kind == kind]
    return _join(c.value for c in sorted(rows, key=lambda c: (not c.is_primary, c.value)))


def _qualification(q) -> str:
    head = q.level.name + (f": {q.title}" if q.title else "")
    year = "studying" if q.currently_studying else q.year_awarded
    detail = _join([q.institution, q.field_of_study, year, q.grade.name if q.grade_id else ""])
    return f"{head} ({detail.replace(SEP, ', ')})" if detail else head


def _experience(e) -> str:
    where = f"{e.role_title}, {e.employer_name}" if e.employer_name else e.role_title
    return f"{where} ({e.months} months)"


def _practical(x) -> str:
    what = f"{x.get_kind_display()}: {x.organisation}"
    return f"{what} ({x.role})" if x.role else what


def _certification(c) -> str:
    detail = _join([c.issuer, c.year_obtained]).replace(SEP, ", ")
    return f"{c.name} ({detail})" if detail else c.name


def _officer(p) -> str:
    u = p.assigned_officer
    return (u.get_full_name() or u.get_username()) if u else ""


ENR = ("enrollments",)
FIELDS: list[tuple[str, str, list[Field]]] = [
    (
        "identity",
        "Identity",
        [
            Field("name", "Name", lambda p: p.full_name_source),
            Field("given_name", "Given name", lambda p: p.given_name),
            Field("family_name", "Family name", lambda p: p.family_name),
            Field("other_names", "Other names", lambda p: p.other_names),
            Field("gender", "Gender", lambda p: p.get_gender_display()),
            Field("age", "Age", lambda p: _age(p)),
            Field("date_of_birth", "Date of birth",
                  lambda p: _date(p.date_of_birth), sensitive=True),
            Field("status", "Status", lambda p: p.get_status_display()),
            Field("county", "County", lambda p: p.origin_county.name if p.origin_county_id else "",
                  select=("origin_county",)),
            Field("assigned_officer", "Assigned officer", _officer, select=("assigned_officer",)),
            Field("registered_on", "Registered on",
                  lambda p: timezone.localtime(p.created_at).date().isoformat()),
            Field("source_ids", "Source IDs",
                  lambda p: _join(f"{s.source}: {s.identifier}"
                                  for s in p.source_identifiers.all()),
                  prefetch=("source_identifiers",)),
        ],
    ),
    (
        "contact",
        "Contact",
        [
            Field("phone", "Phone", lambda p: _contacts(p, "phone"), prefetch=("contacts",),
                  sensitive=True),
            Field("email", "Email", lambda p: _contacts(p, "email"), prefetch=("contacts",),
                  sensitive=True),
        ],
    ),
    (
        "residence",
        "Where they live",
        [
            Field("residence_county", "Residence county",
                  lambda p: (r.county.name if (r := _residence(p)) and r.county_id else ""),
                  prefetch=("residences__county",), sensitive=True),
            Field("sub_county", "Sub-county",
                  lambda p: (r.sub_county_source if (r := _residence(p)) else ""),
                  prefetch=("residences",), sensitive=True),
            Field("ward", "Ward", lambda p: (r.ward_source if (r := _residence(p)) else ""),
                  prefetch=("residences",), sensitive=True),
        ],
    ),
    (
        "enrolment",
        "Programme and cohort",
        [
            Field("programme", "Programme",
                  lambda p: _join(sorted({e.programme.name for e in _enrolments(p)})),
                  prefetch=("enrollments__programme",)),
            Field("cohort", "Cohort",
                  lambda p: _join(sorted({e.cohort_course.cohort.name for e in _enrolments(p)})),
                  prefetch=("enrollments__cohort_course__cohort",)),
            Field("course", "Course",
                  lambda p: _join(e.cohort_course.course.name for e in _enrolments(p)),
                  prefetch=("enrollments__cohort_course__course",)),
            Field("institution", "Training institution",
                  lambda p: _join(sorted({e.institution.name for e in _enrolments(p)})),
                  prefetch=("enrollments__institution",)),
            Field("enrollment_no", "Enrolment number",
                  lambda p: _join(e.source_enrollment_no for e in _enrolments(p)), prefetch=ENR),
            Field("enrollment_status", "Enrolment status",
                  lambda p: _join(e.get_status_display() for e in _enrolments(p)), prefetch=ENR),
            Field("enrolled_on", "Enrolled on",
                  lambda p: _join(_date(e.enrolled_on) for e in _enrolments(p)), prefetch=ENR),
            Field("completed_on", "Completed on",
                  lambda p: _join(_date(e.completed_on) for e in _enrolments(p)), prefetch=ENR),
            Field("exit_reason", "Exit reason",
                  lambda p: _join(e.exit_reason for e in _enrolments(p)), prefetch=ENR),
        ],
    ),
    (
        "education",
        "Education and training",
        [
            Field("highest_qualification", "Highest qualification",
                  lambda p: (_qualification(q[0]) if (q := list(p.qualifications.all())) else ""),
                  prefetch=("qualifications__level", "qualifications__grade")),
            Field("qualifications", "Qualifications",
                  lambda p: _join(_qualification(q) for q in p.qualifications.all()),
                  prefetch=("qualifications__level", "qualifications__grade")),
            Field("certifications", "Certifications",
                  lambda p: _join(_certification(c) for c in p.certifications.all()),
                  prefetch=("certifications",)),
            Field("languages", "Languages",
                  lambda p: _join(f"{x.language} ({x.get_proficiency_display()})"
                                  for x in p.languages.all()),
                  prefetch=("languages",)),
        ],
    ),
    (
        "skills",
        "Skills",
        [
            Field("skills", "Skills",
                  lambda p: _join(f"{s.skill.name} ({s.get_proficiency_display()})"
                                  for s in p.skills.all()),
                  prefetch=("skills__skill",)),
        ],
    ),
    (
        "work",
        "Work experience",
        [
            Field("work_experience", "Work experience",
                  lambda p: _join(_experience(e) for e in p.experience.all()),
                  prefetch=("experience",)),
            Field("months_experience", "Months of work experience",
                  lambda p: sum(e.months for e in p.experience.all()), prefetch=("experience",)),
            Field("practical_experience", "Internships, attachments and volunteering",
                  lambda p: _join(_practical(x) for x in p.practical_experience.all()),
                  prefetch=("practical_experience",)),
        ],
    ),
    (
        "readiness",
        "Work readiness",
        [
            Field("available_from", "Available from",
                  lambda p: _date(r.available_from) if (r := _readiness(p)) else "",
                  select=("readiness",)),
            Field("work_patterns", "Work patterns",
                  lambda p: _patterns(p),
                  select=("readiness",)),
            Field("interest_sectors", "Sectors of interest",
                  lambda p: _join(s.name for s in r.interest_sectors.all())
                  if (r := _readiness(p)) else "",
                  select=("readiness",), prefetch=("readiness__interest_sectors",)),
            Field("preferred_roles", "Preferred roles",
                  lambda p: _join(r.preferred_roles) if (r := _readiness(p)) else "",
                  select=("readiness",)),
            Field("preferred_counties", "Preferred counties",
                  lambda p: _join(c.name for c in r.preferred_counties.all())
                  if (r := _readiness(p)) else "",
                  select=("readiness",), prefetch=("readiness__preferred_counties",)),
            Field("willing_to_relocate", "Willing to relocate",
                  lambda p: _yes_no(r.willing_to_relocate) if (r := _readiness(p)) else "",
                  select=("readiness",)),
            Field("no_work_experience", "Says they have never worked",
                  lambda p: _yes_no(r.no_work_experience) if (r := _readiness(p)) else "",
                  select=("readiness",)),
            Field("readiness_summary", "Introduction",
                  lambda p: r.summary if (r := _readiness(p)) else "", select=("readiness",)),
        ],
    ),
]  # fmt: skip


def _age(p):
    from .services import current_age

    age = current_age(p)
    return "" if age is None else age


BY_KEY = {f.key: f for _g, _l, fields in FIELDS for f in fields}


def groups() -> list[dict]:
    """The catalogue for a picker: ``[{key, label, fields: [{key, label, sensitive}]}]``."""
    return [
        {
            "key": gkey,
            "label": glabel,
            "fields": [{"key": f.key, "label": f.label, "sensitive": f.sensitive} for f in fields],
        }
        for gkey, glabel, fields in FIELDS
    ]


def rows(qs, keys) -> list[dict]:
    """One dict per youth in ``qs``, holding ``_id`` and each requested key this module owns."""
    chosen = [BY_KEY[k] for k in dict.fromkeys(keys) if k in BY_KEY]
    select = {s for f in chosen for s in f.select}
    prefetch = {s for f in chosen for s in f.prefetch}
    qs = qs.select_related(*sorted(select)).prefetch_related(*sorted(prefetch))
    return [{"_id": p.pk} | {f.key: f.get(p) for f in chosen} for p in qs]
