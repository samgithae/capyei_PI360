"""Capability profile of a youth: qualifications, skills, work experience, readiness.

Read and written as one document. A section left out of a write is left alone; a section that is
present replaces what was there, but rows that carry an ``id`` keep their identity and their
verification as long as the facts in them did not change. Audit entries record ids and counts,
not free text."""

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.configuration import services as configuration

from .models import (
    WORK_PATTERNS,
    Participant,
    ParticipantExperience,
    ParticipantQualification,
    ParticipantReadiness,
    ParticipantSkill,
    ProfileFact,
)

PATTERN_CODES = {c for c, _ in WORK_PATTERNS}


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


def _iso(d):
    return d.isoformat() if d else None


def read(p: Participant) -> dict:
    quals = p.qualifications.select_related("level", "verified_by")
    skills = p.skills.select_related("skill", "verified_by")
    exp = p.experience.select_related("sector", "verified_by")
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
                "year_awarded": q.year_awarded,
            }
            for q in quals
        ],
        "skills": [
            {
                **_fact(s),
                "skill_id": str(s.skill_id),
                "skill": s.skill.name,
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
            }
            for e in exp
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


def _sync(p, qs, rows, build, tracked, actor, source):
    """Replace the rows of one section. ``build(row)`` returns field values or raises."""
    existing = {str(o.pk): o for o in qs}
    keep = set()
    for row in rows:
        values = build(row)
        obj = existing.get(str(row.get("id") or ""))
        if obj is None:
            obj = qs.model(participant=p)
        elif all(getattr(obj, k) == v for k, v in values.items() if k in tracked):
            keep.add(str(obj.pk))
            continue  # nothing changed: keep it and its verification
        for k, v in values.items():
            setattr(obj, k, v)
        _stamp(obj, actor, source)
        obj.save()
        keep.add(str(obj.pk))
    for key, obj in existing.items():
        if key not in keep:
            obj.delete()
    return len(keep)


@transaction.atomic
def write(*, actor, p: Participant, data: dict, source=ProfileFact.STAFF) -> dict:
    counts = {}

    if "qualifications" in data:

        def qual(r):
            level = _lookup("qualification-levels", r["level_id"], "qualification level")
            return {
                "level": level,
                "title": r.get("title", "").strip(),
                "institution": r.get("institution", "").strip(),
                "year_awarded": r.get("year_awarded"),
            }

        counts["qualifications"] = _sync(
            p,
            ParticipantQualification.objects.filter(participant=p),
            data["qualifications"],
            qual,
            {"level", "title", "institution", "year_awarded"},
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
            return {
                "role_title": r["role_title"].strip(),
                "employer_name": r.get("employer_name", "").strip(),
                "sector": _lookup("sectors", sector, "sector") if sector else None,
                "months": r["months"],
            }

        counts["experience"] = _sync(
            p,
            ParticipantExperience.objects.filter(participant=p),
            data["experience"],
            exp,
            {"role_title", "employer_name", "sector", "months"},
            actor,
            source,
        )

    if "readiness" in data:
        r = data["readiness"]
        patterns = r.get("work_patterns", [])
        bad = [x for x in patterns if x not in PATTERN_CODES]
        if bad:
            raise ProfileError(f"Unknown work pattern: {bad[0]}.", "work_patterns")
        sectors = [_lookup("sectors", i, "sector") for i in r.get("interest_sector_ids", [])]
        row, _ = ParticipantReadiness.objects.get_or_create(participant=p)
        changed = (
            row.available_from != r.get("available_from")
            or sorted(row.work_patterns) != sorted(patterns)
            or set(row.interest_sectors.values_list("pk", flat=True)) != {s.pk for s in sectors}
        )
        if changed or row.source is None:
            row.available_from = r.get("available_from")
            row.work_patterns = sorted(patterns)
            _stamp(row, actor, source)
            row.save()
            row.interest_sectors.set(sectors)
        counts["readiness"] = 1

    if counts:
        audit.record(
            actor=actor,
            action="participant.profile_edited",
            object_type="participant",
            object_id=p.pk,
            after={"counts": counts, "source": source},
        )
    return read(p)


KINDS = {
    "qualification": ParticipantQualification,
    "skill": ParticipantSkill,
    "experience": ParticipantExperience,
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
    audit.record(
        actor=actor,
        action="participant.profile_verified" if verified else "participant.profile_unverified",
        object_type="participant",
        object_id=p.pk,
        after={"kind": kind, "id": str(obj.pk)},
    )
    return read(p)


def options() -> dict:
    """What the profile form may choose from."""
    return {
        **configuration.profile_options(),
        "work_patterns": [{"id": c, "name": n} for c, n in WORK_PATTERNS],
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

    for pid, rows in grouped(ParticipantQualification.objects.select_related("level")).items():
        top = max(rows, key=lambda q: q.level.rank)
        put(pid, "participant.education_level", top.level.rank, [top])
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
