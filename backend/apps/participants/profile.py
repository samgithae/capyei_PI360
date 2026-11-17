"""Capability profile of a youth: the CV data and what the compatibility rules read.

Qualifications, skills, work experience, certifications, practical experience, languages and
readiness (summary, preferences, availability). Read and written as one document. A section left
out of a write is left alone; a section that is present replaces what was there, but rows that
carry an ``id`` keep their identity and their verification as long as the facts in them did not
change. Inside ``readiness`` only the keys sent are changed. Audit entries record ids and counts,
not free text."""

from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.configuration import services as configuration

from .models import (
    EMPLOYMENT_TYPES,
    LANGUAGE_LEVELS,
    PRACTICAL_KINDS,
    WORK_PATTERNS,
    Participant,
    ParticipantCertification,
    ParticipantExperience,
    ParticipantLanguage,
    ParticipantPractical,
    ParticipantQualification,
    ParticipantReadiness,
    ParticipantSkill,
    ProfileFact,
    ProfileVerification,
)

PATTERN_CODES = {c for c, _ in WORK_PATTERNS}
EMPLOYMENT_CODES = {c for c, _ in EMPLOYMENT_TYPES}
PRACTICAL_CODES = {c for c, _ in PRACTICAL_KINDS}
LANGUAGE_CODES = {c for c, _ in LANGUAGE_LEVELS}
# Offered as suggestions in the language field; anything else may be typed.
COMMON_LANGUAGES = ["English", "Kiswahili", "French", "Arabic", "Kikuyu", "Luo", "Kalenjin"]
SUMMARY_MAX = 600
SECTIONS = ("qualifications", "skills", "experience", "certifications", "practical", "languages")


class ProfileError(ValueError):
    def __init__(self, message, field="profile"):
        super().__init__(message)
        self.field = field


def _fact(f):
    return {
        "id": str(f.pk),
        "source": f.source,
        "verified": f.verified,
        "verified_at": f.verified_at.isoformat() if f.verified_at else None,
        "verified_by": f.verified_by.get_username() if f.verified_by_id else "",
    }


def _hide_staff(doc: dict) -> dict:
    """The same document without the names of the staff who verified entries."""
    for key in SECTIONS:
        for row in doc[key]:
            row["verified_by"] = ""
    doc["readiness"]["verified_by"] = ""
    return doc


def _iso(d):
    return d.isoformat() if d else None


def read(p: Participant, *, hide_staff: bool = False) -> dict:
    doc = _read(p)
    if hide_staff:
        return _hide_staff(doc)
    _attach_verification(p, doc)
    return doc


def _attach_verification(p: Participant, doc: dict) -> None:
    """Add the staff check detail (status, method, note) to each entry that has one."""
    rows = {
        str(v.fact_id): v
        for v in ProfileVerification.objects.filter(participant=p).select_related("decided_by")
    }
    for key in (*SECTIONS, "readiness"):
        for row in doc[key] if key != "readiness" else [doc[key]]:
            v = rows.get(row.get("id") or "")
            row["verification"] = (
                {
                    "status": v.status,
                    "method": v.method,
                    "notes": v.notes,
                    "decided_by": v.decided_by.get_username() if v.decided_by_id else "",
                    "decided_at": v.decided_at.isoformat() if v.decided_at else None,
                }
                if v
                else None
            )


def _read(p: Participant) -> dict:
    quals = p.qualifications.select_related("level", "grade", "verified_by")
    skills = p.skills.select_related("skill", "verified_by")
    exp = p.experience.select_related("sector", "verified_by")
    certs = p.certifications.select_related("verified_by")
    practical = p.practical_experience.select_related("verified_by")
    languages = p.languages.select_related("verified_by")
    ready = ParticipantReadiness.objects.filter(participant=p).select_related("verified_by").first()
    top = quals.first()
    return {
        "qualifications": [
            {
                **_fact(q),
                "level_id": str(q.level_id),
                "level": q.level.name,
                "rank": q.level.rank,
                "title": q.title,
                "institution": q.institution,
                "field_of_study": q.field_of_study,
                "start_year": q.start_year,
                "year_awarded": q.year_awarded,
                "currently_studying": q.currently_studying,
                "grade_id": str(q.grade_id) if q.grade_id else None,
                "grade": q.grade.name if q.grade_id else "",
                "grade_rank": q.grade.rank if q.grade_id else None,
            }
            for q in quals
        ],
        "skills": [
            {
                **_fact(s),
                "skill_id": str(s.skill_id),
                "skill": s.skill.name,
                "category": s.skill.category,
                "proficiency": s.proficiency,
            }
            for s in skills
        ],
        "experience": [
            {
                **_fact(e),
                "role_title": e.role_title,
                "employer_name": e.employer_name,
                "sector_id": str(e.sector_id) if e.sector_id else None,
                "sector": e.sector.name if e.sector_id else "",
                "months": e.months,
                "employment_type": e.employment_type,
                "start_date": _iso(e.start_date),
                "end_date": _iso(e.end_date),
                "is_current": e.is_current,
                "responsibilities": e.responsibilities,
                "achievements": e.achievements,
            }
            for e in exp
        ],
        "certifications": [
            {
                **_fact(c),
                "name": c.name,
                "issuer": c.issuer,
                "year_obtained": c.year_obtained,
                "expiry_date": _iso(c.expiry_date),
            }
            for c in certs
        ],
        "practical": [
            {
                **_fact(x),
                "organisation": x.organisation,
                "role": x.role,
                "kind": x.kind,
                "start_date": _iso(x.start_date),
                "end_date": _iso(x.end_date),
                "description": x.description,
            }
            for x in practical
        ],
        "languages": [
            {**_fact(x), "language": x.language, "proficiency": x.proficiency} for x in languages
        ],
        "readiness": {
            **(_fact(ready) if ready else {"id": None, "source": None, "verified": False}),
            "available_from": _iso(ready.available_from) if ready else None,
            "work_patterns": list(ready.work_patterns) if ready else [],
            "interest_sector_ids": (
                [str(i) for i in ready.interest_sectors.values_list("pk", flat=True)]
                if ready
                else []
            ),
            "interest_sectors": (
                [s.name for s in ready.interest_sectors.order_by("name")] if ready else []
            ),
            "summary": ready.summary if ready else "",
            "preferred_roles": list(ready.preferred_roles) if ready else [],
            "preferred_county_ids": (
                [str(i) for i in ready.preferred_counties.values_list("pk", flat=True)]
                if ready
                else []
            ),
            "preferred_counties": (
                [c.name for c in ready.preferred_counties.order_by("name")] if ready else []
            ),
            "willing_to_relocate": ready.willing_to_relocate if ready else None,
            "no_work_experience": ready.no_work_experience if ready else False,
        },
        "summary": {
            "highest_qualification": top.level.name if top else "",
            "experience_months": sum(e.months for e in exp),
            "skills": [s.skill.name for s in skills],
        },
    }


def _lookup(key, pk, label):
    found = configuration.active_reference(key, pk)
    if found is None:
        raise ProfileError(f"Unknown {label}.", label)
    return found


def _stamp(obj, actor, source):
    obj.source, obj.entered_by = source, actor
    obj.verified_by, obj.verified_at = None, None


def _reassess(obj):
    """An entry that staff had verified changed: its check no longer applies, say so."""
    ProfileVerification.objects.filter(fact_id=obj.pk, status=ProfileVerification.VERIFIED).update(
        status=ProfileVerification.REASSESS
    )
    ProfileVerification.objects.filter(fact_id=obj.pk, status=ProfileVerification.REJECTED).update(
        status=ProfileVerification.PENDING
    )


def _sync(p, qs, rows, build, tracked, actor, source):
    """Replace the rows of one section. ``build(row)`` returns field values or raises.
    ``tracked`` is the set of fields whose change clears verification, or a function of the
    built values that returns it."""
    existing = {str(o.pk): o for o in qs}
    keep = set()
    for row in rows:
        values = build(row)
        names = tracked(values) if callable(tracked) else tracked
        obj = existing.get(str(row.get("id") or ""))
        if obj is None:
            obj = qs.model(participant=p)
        elif all(getattr(obj, k) == v for k, v in values.items() if k in names):
            keep.add(str(obj.pk))
            continue  # nothing changed: keep it and its verification
        changed_existing = obj.pk is not None and str(obj.pk) in existing
        for k, v in values.items():
            setattr(obj, k, v)
        _stamp(obj, actor, source)
        obj.save()
        if changed_existing:
            _reassess(obj)
        keep.add(str(obj.pk))
    for key, obj in existing.items():
        if key not in keep:
            if source == ProfileFact.YOUTH and obj.verified:
                raise ProfileError(
                    "An entry checked by staff cannot be removed here. Ask your officer.",
                    "verified",
                )
            ProfileVerification.objects.filter(fact_id=obj.pk).delete()
            obj.delete()
    return len(keep)


def _text(r, key):
    return (r.get(key) or "").strip()


def _months_between(start: date, end: date) -> int:
    return max(0, (end.year - start.year) * 12 + end.month - start.month)


def _check_dates(start, end, field):
    if start and end and end < start:
        raise ProfileError("The end date cannot be before the start date.", field)


@transaction.atomic
def write(*, actor, p: Participant, data: dict, source=ProfileFact.STAFF) -> dict:
    counts = {}

    if "qualifications" in data:

        def qual(r):
            level = _lookup("qualification-levels", r["level_id"], "qualification level")
            grade = None
            if r.get("grade_id"):
                grade = configuration.active_grade(level.pk, r["grade_id"])
                if grade is None:
                    raise ProfileError("That grade does not belong to this level.", "grade")
            studying = bool(r.get("currently_studying"))
            start, done = r.get("start_year"), r.get("year_awarded")
            if studying:
                done = None  # still studying: no completion year
            if start and done and done < start:
                raise ProfileError("The completion year is before the start year.", "year")
            return {
                "level": level,
                "title": _text(r, "title"),
                "institution": _text(r, "institution"),
                "field_of_study": _text(r, "field_of_study"),
                "start_year": start,
                "year_awarded": done,
                "currently_studying": studying,
                "grade": grade,
            }

        counts["qualifications"] = _sync(
            p,
            ParticipantQualification.objects.filter(participant=p),
            data["qualifications"],
            qual,
            {
                "level",
                "title",
                "institution",
                "field_of_study",
                "start_year",
                "year_awarded",
                "currently_studying",
                "grade",
            },
            actor,
            source,
        )

    if "skills" in data:
        ids = [str(r["skill_id"]) for r in data["skills"]]
        if len(set(ids)) < len(ids):
            raise ProfileError("A skill can be listed only once.", "skills")

        def skill(r):
            return {
                "skill": _lookup("skills", r["skill_id"], "skill"),
                "proficiency": r.get("proficiency") or ParticipantSkill.WORKING,
            }

        counts["skills"] = _sync(
            p,
            ParticipantSkill.objects.filter(participant=p),
            data["skills"],
            skill,
            {"skill", "proficiency"},
            actor,
            source,
        )

    if "experience" in data:

        def exp(r):
            sector = r.get("sector_id")
            kind = r.get("employment_type") or ""
            if kind and kind not in EMPLOYMENT_CODES:
                raise ProfileError("Unknown employment type.", "employment_type")
            start, end = r.get("start_date"), r.get("end_date")
            current = bool(r.get("is_current"))
            if current:
                end = None  # still working there
            _check_dates(start, end, "experience")
            if start:  # worked out from the dates, so it is never asked for twice
                months = _months_between(start, end or timezone.localdate())
            elif r.get("months") is not None:
                months = r["months"]
            else:
                raise ProfileError("Give the start date, or how many months you worked.", "months")
            return {
                "role_title": r["role_title"].strip(),
                "employer_name": _text(r, "employer_name"),
                "sector": _lookup("sectors", sector, "sector") if sector else None,
                "months": months,
                "employment_type": kind,
                "start_date": start,
                "end_date": end,
                "is_current": current,
                "responsibilities": _text(r, "responsibilities"),
                "achievements": _text(r, "achievements"),
            }

        base = {
            "role_title",
            "employer_name",
            "sector",
            "employment_type",
            "start_date",
            "end_date",
            "is_current",
            "responsibilities",
            "achievements",
        }
        counts["experience"] = _sync(
            p,
            ParticipantExperience.objects.filter(participant=p),
            data["experience"],
            exp,
            # Months is derived from the dates; it is a fact only when there are no dates.
            lambda v: base | ({"months"} if v["start_date"] is None else set()),
            actor,
            source,
        )

    if "certifications" in data:

        def cert(r):
            return {
                "name": r["name"].strip(),
                "issuer": _text(r, "issuer"),
                "year_obtained": r.get("year_obtained"),
                "expiry_date": r.get("expiry_date"),
            }

        counts["certifications"] = _sync(
            p,
            ParticipantCertification.objects.filter(participant=p),
            data["certifications"],
            cert,
            {"name", "issuer", "year_obtained", "expiry_date"},
            actor,
            source,
        )

    if "practical" in data:

        def practical(r):
            if r["kind"] not in PRACTICAL_CODES:
                raise ProfileError("Unknown kind of practical experience.", "kind")
            _check_dates(r.get("start_date"), r.get("end_date"), "practical")
            return {
                "organisation": r["organisation"].strip(),
                "role": _text(r, "role"),
                "kind": r["kind"],
                "start_date": r.get("start_date"),
                "end_date": r.get("end_date"),
                "description": _text(r, "description"),
            }

        counts["practical"] = _sync(
            p,
            ParticipantPractical.objects.filter(participant=p),
            data["practical"],
            practical,
            {"organisation", "role", "kind", "start_date", "end_date", "description"},
            actor,
            source,
        )

    if "languages" in data:
        names = [r["language"].strip().lower() for r in data["languages"]]
        if len(set(names)) < len(names):
            raise ProfileError("A language can be listed only once.", "languages")

        def language(r):
            level = r.get("proficiency") or "fluent"
            if level not in LANGUAGE_CODES:
                raise ProfileError("Unknown language level.", "proficiency")
            return {"language": r["language"].strip(), "proficiency": level}

        counts["languages"] = _sync(
            p,
            ParticipantLanguage.objects.filter(participant=p),
            data["languages"],
            language,
            {"language", "proficiency"},
            actor,
            source,
        )

    if "readiness" in data:
        counts["readiness"] = _write_readiness(p, data["readiness"], actor, source)

    if counts:
        audit.record(
            actor=actor,
            action="participant.profile_edited",
            object_type="participant",
            object_id=p.pk,
            after={"counts": counts, "source": source},
        )
    return read(p)


def _write_readiness(p, r, actor, source) -> int:
    """Change only the readiness keys that were sent; the rest stay as they are."""
    row, _ = ParticipantReadiness.objects.get_or_create(participant=p)
    new = {}
    if "available_from" in r:
        new["available_from"] = r["available_from"]
    if "work_patterns" in r:
        bad = [x for x in r["work_patterns"] if x not in PATTERN_CODES]
        if bad:
            raise ProfileError(f"Unknown work pattern: {bad[0]}.", "work_patterns")
        new["work_patterns"] = sorted(r["work_patterns"])
    if "summary" in r:
        new["summary"] = (r["summary"] or "").strip()
        if len(new["summary"]) > SUMMARY_MAX:
            raise ProfileError(f"Keep the summary under {SUMMARY_MAX} characters.", "summary")
    if "preferred_roles" in r:
        roles = [x.strip() for x in r["preferred_roles"] if x.strip()]
        new["preferred_roles"] = list(dict.fromkeys(roles))  # no repeats, order kept
    if "willing_to_relocate" in r:
        new["willing_to_relocate"] = r["willing_to_relocate"]
    if "no_work_experience" in r:
        new["no_work_experience"] = bool(r["no_work_experience"])
    sectors = (
        [_lookup("sectors", i, "sector") for i in r["interest_sector_ids"]]
        if "interest_sector_ids" in r
        else None
    )
    counties = None
    if "preferred_county_ids" in r:
        counties = []
        for i in r["preferred_county_ids"]:
            if not configuration.county_exists(i):
                raise ProfileError("Unknown county.", "preferred_county_ids")
            counties.append(i)
    changed = row.source is None or any(getattr(row, k) != v for k, v in new.items())
    if sectors is not None:
        changed = changed or set(row.interest_sectors.values_list("pk", flat=True)) != {
            s.pk for s in sectors
        }
    if counties is not None:
        changed = changed or {
            str(i) for i in row.preferred_counties.values_list("pk", flat=True)
        } != {str(i) for i in counties}
    if changed:
        for k, v in new.items():
            setattr(row, k, v)
        _stamp(row, actor, source)
        row.save()
        if sectors is not None:
            row.interest_sectors.set(sectors)
        if counties is not None:
            row.preferred_counties.set(counties)
    return 1


KINDS = {
    "qualification": ParticipantQualification,
    "skill": ParticipantSkill,
    "experience": ParticipantExperience,
    "certification": ParticipantCertification,
    "practical": ParticipantPractical,
    "language": ParticipantLanguage,
    "readiness": ParticipantReadiness,
}


@transaction.atomic
def verify(*, actor, p: Participant, kind: str, fact_id, verified: bool) -> dict:
    model = KINDS.get(kind)
    if model is None:
        raise ProfileError("Unknown kind of fact.", "kind")
    try:
        obj = model.objects.get(pk=fact_id, participant=p)
    except (model.DoesNotExist, ValueError):
        raise ProfileError("That entry was not found.", "id") from None
    obj.verified_by = actor if verified else None
    obj.verified_at = timezone.now() if verified else None
    obj.save(update_fields=["verified_by", "verified_at", "updated_at"])
    _upsert_verification(
        p,
        kind,
        obj,
        actor,
        ProfileVerification.VERIFIED if verified else ProfileVerification.PENDING,
    )
    audit.record(
        actor=actor,
        action="participant.profile_verified" if verified else "participant.profile_unverified",
        object_type="participant",
        object_id=p.pk,
        after={"kind": kind, "id": str(obj.pk)},
    )
    return read(p)


def _upsert_verification(p, kind, obj, actor, status, method="", notes=""):
    ProfileVerification.objects.update_or_create(
        fact_id=obj.pk,
        defaults={
            "participant": p,
            "kind": kind,
            "status": status,
            "method": method,
            "notes": notes,
            "decided_by": actor,
            "decided_at": timezone.now(),
        },
    )


METHOD_CODES = {c for c, _ in ProfileVerification.METHODS}
STATUS_CODES = {c for c, _ in ProfileVerification.STATUSES}


@transaction.atomic
def record_verification(
    *, actor, p: Participant, kind: str, fact_id, status: str, method: str = "", notes: str = ""
) -> dict:
    """Record the outcome of checking one entry. Only ``verified`` makes the entry count as
    verified for the matching rules; every other status clears that mark."""
    model = KINDS.get(kind)
    if model is None:
        raise ProfileError("Unknown kind of fact.", "kind")
    if status not in STATUS_CODES:
        raise ProfileError("Unknown verification status.", "status")
    if method and method not in METHOD_CODES:
        raise ProfileError("Unknown verification method.", "method")
    notes = (notes or "").strip()
    if status == ProfileVerification.VERIFIED and not method:
        raise ProfileError("Say how it was checked.", "method")
    if status == ProfileVerification.REJECTED and not notes:
        raise ProfileError("Say why it was rejected.", "notes")
    try:
        obj = model.objects.get(pk=fact_id, participant=p)
    except (model.DoesNotExist, ValueError):
        raise ProfileError("That entry was not found.", "id") from None
    ok = status == ProfileVerification.VERIFIED
    obj.verified_by = actor if ok else None
    obj.verified_at = timezone.now() if ok else None
    obj.save(update_fields=["verified_by", "verified_at", "updated_at"])
    _upsert_verification(p, kind, obj, actor, status, method, notes)
    audit.record(
        actor=actor,
        action="participant.profile_verification",
        object_type="participant",
        object_id=p.pk,
        after={"kind": kind, "id": str(obj.pk), "status": status, "method": method},
    )
    return read(p)


def options() -> dict:
    """What the profile form may choose from."""
    return {
        **configuration.profile_options(),
        "work_patterns": [{"id": c, "name": n} for c, n in WORK_PATTERNS],
        "employment_types": [{"id": c, "name": n} for c, n in EMPLOYMENT_TYPES],
        "practical_kinds": [{"id": c, "name": n} for c, n in PRACTICAL_KINDS],
        "language_levels": [{"id": c, "name": n} for c, n in LANGUAGE_LEVELS],
        "languages": COMMON_LANGUAGES,
        "verification_methods": [{"id": c, "name": n} for c, n in ProfileVerification.METHODS],
        "verification_statuses": [{"id": c, "name": n} for c, n in ProfileVerification.STATUSES],
        "counties": [
            {"id": c["id"], "name": c["name"]} for c in configuration.filter_options()["counties"]
        ],
    }


# ---- what the rules read ---------------------------------------------------------------------


def _provenance(rows):
    """Where a group of facts came from and whether staff verified all of them."""
    sources = {r.source for r in rows}
    source = (
        "self-reported"
        if ProfileFact.YOUTH in sources
        else ("import" if sources == {ProfileFact.IMPORT} else "staff")
    )
    return {"source": source, "verified": all(r.verified for r in rows)}


def capability_snapshots(participant_ids) -> dict:
    """``{participant_id: {"name", "snapshot"}}`` for youth with at least one recorded fact.

    The snapshot holds only the fields the compatibility rules read. A fact that is not recorded
    is left out, so the engine reports it as unknown rather than failing the youth. Qualification
    is the highest level's rank; skills map skill id to proficiency (1 to 3); experience is the
    total of months recorded."""
    ids = list(participant_ids)
    people = {p.pk: p for p in Participant.objects.filter(pk__in=ids)}
    out: dict = {pid: {"snapshot": {}} for pid in people}

    def put(pid, name, value, rows):
        out[pid]["snapshot"][name] = {"value": value, **_provenance(rows)}

    def grouped(qs):
        rows: dict = {}
        for r in qs.filter(participant_id__in=people).select_related():
            rows.setdefault(r.participant_id, []).append(r)
        return rows

    for pid, rows in grouped(
        ParticipantQualification.objects.select_related("level", "grade")
    ).items():
        top = max(rows, key=lambda q: q.level.rank)
        put(pid, "participant.education_level", top.level.rank, [top])
        at_top = [q for q in rows if q.level_id == top.level_id and q.grade_id]
        best = max(at_top, key=lambda q: q.grade.rank) if at_top else None
        put(
            pid,
            "participant.education_grade",
            {
                "level_rank": top.level.rank,
                "grade_rank": best.grade.rank if best else None,
                "grade": best.grade.name if best else "",
            },
            [best or top],
        )
    for pid, rows in grouped(ParticipantSkill.objects).items():
        put(pid, "participant.skills", {str(r.skill_id): r.proficiency for r in rows}, rows)
    for pid, rows in grouped(ParticipantExperience.objects).items():
        put(pid, "participant.experience_months", sum(r.months for r in rows), rows)
    for r in ParticipantReadiness.objects.filter(participant_id__in=people):
        if r.available_from:
            put(r.participant_id, "participant.available_from", r.available_from.isoformat(), [r])
        if r.work_patterns:
            put(r.participant_id, "participant.acceptable_work_patterns", r.work_patterns, [r])
        sectors = [str(s) for s in r.interest_sectors.values_list("pk", flat=True)]
        if sectors:
            put(r.participant_id, "participant.interest_sectors", sectors, [r])
    return {
        str(pid): {"name": people[pid].full_name_source, "snapshot": d["snapshot"]}
        for pid, d in out.items()
        if d["snapshot"]
    }
