"""Public interface of apps.employers (T-044). Every change is audited in the same transaction."""

from collections import Counter
from datetime import date
from difflib import SequenceMatcher

from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.audit import services as audit
from apps.configuration import services as configuration
from apps.configuration.services import normalise as norm

from .models import (
    ClusterDecision,
    Employer,
    EmployerAlias,
    EmployerContact,
    EmployerCounty,
    Opportunity,
    OpportunityCounty,
    OpportunityRequirement,
)

SIMILAR = (
    0.88  # name similarity that triggers the duplicate warning; steward decides, never auto-merged
)
FIELDS = ("name", "sub_county", "address", "website", "status", "notes")
# Many-to-many links, given as lists of reference ids: payload key -> (attribute, reference kind).
LINKS = {"sector_ids": ("sectors", "sectors"), "county_ids": ("counties", "counties")}
SINGULAR = {"sectors": "sector", "counties": "county"}


class DuplicateWarning(Exception):
    def __init__(self, matches):
        self.matches = matches


def exists(employer_id) -> bool:
    return Employer.objects.filter(pk=employer_id).exists()


def find_similar(name, *, exclude=None):
    """Existing employers whose name is the same after normalising, or nearly so."""
    key = norm(name)
    if not key:
        return []
    out = []
    for e in Employer.objects.filter(archived_at__isnull=True).exclude(pk=exclude):
        ratio = (
            1.0
            if e.name_normalised == key
            else SequenceMatcher(None, key, e.name_normalised).ratio()
        )
        if ratio >= SIMILAR:
            out.append(
                {"id": str(e.pk), "name": e.name, "status": e.status, "score": round(ratio, 2)}
            )
    return sorted(out, key=lambda m: -m["score"])


def _snapshot(e):
    out = {f: (str(getattr(e, f)) if getattr(e, f) is not None else None) for f in FIELDS}
    for key, (attr, _kind) in LINKS.items():
        out[key] = _link_ids(e, attr) if e.pk else []
    return out


def _link_ids(obj, attr):
    """Ids of the linked reference rows, sorted so before/after audit snapshots compare."""
    return sorted(str(i) for i in getattr(obj, attr).values_list("pk", flat=True))


def _unique(ids):
    """Duplicates are normalised away (first occurrence wins) rather than rejected."""
    return list(dict.fromkeys(str(i) for i in ids))


def _resolve(kind, ids, field, *, allowed=None, owner="", keep=()):
    """Reference rows for ``ids``. Each must exist and be active (``keep`` ids may be retired:
    they are links already stored, kept as history). When ``allowed`` is given, each must also be
    one of those ids, else the error names what to do about it."""
    ids = _unique(ids)
    rows = configuration.references_by_id(kind, ids)
    noun = SINGULAR[kind]
    missing = [i for i in ids if i not in rows]
    if missing:
        raise RuleViolation(field, f"Unknown {noun}: {', '.join(missing)}.", "unknown")
    retired = [rows[i].name for i in ids if not rows[i].active and i not in keep]
    if retired:
        raise RuleViolation(
            field, f"{', '.join(retired)} is no longer in use; choose another {noun}.", "inactive"
        )
    if allowed is not None:
        outside = [rows[i].name for i in ids if i not in allowed]
        if outside:
            raise RuleViolation(
                field,
                f"{', '.join(outside)} {'is' if len(outside) == 1 else 'are'} not among "
                f"{owner}'s {kind}. Add {'it' if len(outside) == 1 else 'them'} to the employer "
                f"profile first, or remove {'it' if len(outside) == 1 else 'them'} here.",
                f"{noun}_not_in_employer",
            )
    return [rows[i] for i in ids]


def _check_not_in_use(employer, key, rows):
    """Refuse to drop a county or sector that a draft or open opportunity of this employer still
    uses; closed, expired and archived ones keep it as history."""
    attr, _kind = LINKS[key]
    dropped = set(_link_ids(employer, attr)) - {str(r.pk) for r in rows}
    if not dropped:
        return
    live = Opportunity.objects.filter(
        employer=employer,
        archived_at__isnull=True,
        status__in=[Opportunity.DRAFT, Opportunity.OPEN],
        **{f"{attr}__in": dropped},
    ).distinct()
    if (first := live.first()) is not None:
        names = ", ".join(
            getattr(employer, attr).filter(pk__in=dropped).values_list("name", flat=True)
        )
        raise RuleViolation(
            key,
            f"Cannot remove {names}: the opportunity \u201c{first.title}\u201d still uses it"
            f"{'' if live.count() == 1 else f' (and {live.count() - 1} more)'}. "
            f"Change those opportunities first.",
            "in_use",
        )


@transaction.atomic
def create_employer(*, actor, data, confirm_duplicate=False):
    if not confirm_duplicate and (matches := find_similar(data["name"])):
        raise DuplicateWarning(matches)
    data = dict(data)
    links = {k: data.pop(k) for k in LINKS if k in data}
    resolved = {k: _resolve(LINKS[k][1], v, k) for k, v in links.items()}
    e = Employer.objects.create(**data)
    for k, rows in resolved.items():
        getattr(e, LINKS[k][0]).set(rows)
    audit.record(
        actor=actor, action="employer.created", object_type="employer", object_id=e.pk,
        after=_snapshot(e),
    )  # fmt: skip
    return e


@transaction.atomic
def update_employer(*, actor, employer, data, confirm_duplicate=False):
    if (
        "name" in data
        and norm(data["name"]) != employer.name_normalised
        and not confirm_duplicate
        and (matches := find_similar(data["name"], exclude=employer.pk))
    ):
        raise DuplicateWarning(matches)
    before = _snapshot(employer)
    data = dict(data)
    links = {k: data.pop(k) for k in LINKS if k in data}
    resolved = {k: _resolve(LINKS[k][1], v, k, keep=before[k]) for k, v in links.items()}
    for k, rows in resolved.items():
        _check_not_in_use(employer, k, rows)
    for k, v in data.items():
        setattr(employer, k, v)
    employer.save()
    for k, rows in resolved.items():
        getattr(employer, LINKS[k][0]).set(rows)
    after = _snapshot(employer)
    changed = [k for k in after if after[k] != before[k]]
    if changed:
        audit.record(
            actor=actor, action="employer.updated", object_type="employer", object_id=employer.pk,
            before={k: before[k] for k in changed}, after={k: after[k] for k in changed},
        )  # fmt: skip
    return employer


@transaction.atomic
def save_contact(*, actor, employer, data, contact=None):
    """Create or update a contact; making one primary demotes the previous primary."""
    if data.get("is_primary"):
        employer.contacts.exclude(pk=getattr(contact, "pk", None)).update(is_primary=False)
    if contact is None:
        contact = EmployerContact.objects.create(employer=employer, **data)
        action, before = "employer.contact_added", None
    else:
        before = {k: getattr(contact, k) for k in data}
        for k, v in data.items():
            setattr(contact, k, v)
        contact.save()
        action = "employer.contact_updated"
    audit.record(
        actor=actor, action=action, object_type="employer", object_id=employer.pk,
        before=before, after={"contact": str(contact.pk), **data},
    )  # fmt: skip
    return contact


@transaction.atomic
def remove_contact(*, actor, employer, contact):
    snap = {"contact": str(contact.pk), "name": contact.name}
    contact.delete()
    audit.record(
        actor=actor, action="employer.contact_removed", object_type="employer",
        object_id=employer.pk, before=snap,
    )  # fmt: skip


def history(employer):
    return audit.history("employer", employer.pk)


# --- opportunities (T-045, FR-12..FR-15) -----------------------------------------------------

OPP_FIELDS = (
    "title", "kind", "location", "positions", "description", "start_date", "closing_date",
)  # fmt: skip


class RuleViolation(Exception):
    def __init__(self, field, message, code):
        super().__init__(message)
        self.field, self.message, self.code = field, message, code


def _opp_snapshot(o):
    out = {f: (None if getattr(o, f) is None else str(getattr(o, f))) for f in OPP_FIELDS}
    out["employer"] = str(o.employer_id)
    for key, (attr, _kind) in LINKS.items():
        out[key] = _link_ids(o, attr) if o.pk else []
    return out


def _check_dates(start, closing):
    if start and closing and closing < start:
        raise RuleViolation("closing_date", "Closing date is before the start date.", "bad_dates")


def _opportunity_links(employer, data, opportunity=None, *, employer_changed=False):
    """Resolve the counties and sectors an opportunity will have, each a subset of its employer's.

    Links the opportunity already stores stay valid (older records may predate this rule and are
    kept as history); anything newly added must belong to the employer. When the employer changes
    nothing is carried over unchecked: the stored links are re-validated against the new one."""
    out = {}
    for key, (attr, kind) in LINKS.items():
        stored = _link_ids(opportunity, attr) if opportunity else []
        if key in data:
            ids = data[key]
        elif employer_changed:
            ids = stored
        else:
            continue
        keep = [] if employer_changed else stored
        allowed = set(_link_ids(employer, attr)) | set(keep)
        out[key] = _resolve(kind, ids, key, allowed=allowed, owner=employer.name, keep=keep)
    return out


@transaction.atomic
def create_opportunity(*, actor, employer, data):
    if employer.status == Employer.INACTIVE:
        raise RuleViolation("employer", "Employer is inactive.", "employer_inactive")
    data = dict(data)
    _check_dates(data.get("start_date"), data.get("closing_date"))
    links = _opportunity_links(employer, {k: data.pop(k) for k in LINKS if k in data})
    o = Opportunity.objects.create(employer=employer, **data)
    for key, rows in links.items():
        getattr(o, LINKS[key][0]).set(rows)
    audit.record(
        actor=actor, action="opportunity.created", object_type="opportunity", object_id=o.pk,
        after=_opp_snapshot(o),
    )  # fmt: skip
    return o


@transaction.atomic
def update_opportunity(*, actor, opportunity, data):
    if opportunity.status in (Opportunity.CLOSED, Opportunity.EXPIRED):
        raise RuleViolation("status", "Reopen the opportunity before editing it.", "locked")
    data = dict(data)
    employer = data.pop("employer", None) or opportunity.employer
    changed_employer = employer.pk != opportunity.employer_id
    if changed_employer:
        if opportunity.status != Opportunity.DRAFT:
            raise RuleViolation(
                "employer_id",
                "The employer can only be changed while the opportunity is a draft.",
                "employer_locked",
            )
        if employer.status == Employer.INACTIVE or employer.archived_at is not None:
            raise RuleViolation("employer_id", "Choose an active employer.", "employer_inactive")
    merged = {**{f: getattr(opportunity, f) for f in ("start_date", "closing_date")}, **data}
    _check_dates(merged["start_date"], merged["closing_date"])
    if (
        opportunity.status == Opportunity.OPEN
        and merged["closing_date"]
        and merged["closing_date"] < date.today()
    ):
        raise RuleViolation("closing_date", "Closing date is in the past.", "past_closing")
    links = _opportunity_links(
        employer, {k: data.pop(k) for k in LINKS if k in data}, opportunity,
        employer_changed=changed_employer,
    )  # fmt: skip
    before = _opp_snapshot(opportunity)
    for k, v in data.items():
        setattr(opportunity, k, v)
    opportunity.employer = employer
    opportunity.save()
    for key, rows in links.items():
        getattr(opportunity, LINKS[key][0]).set(rows)
    after = _opp_snapshot(opportunity)
    changed = [k for k in after if after[k] != before[k]]
    if changed:
        audit.record(
            actor=actor, action="opportunity.updated", object_type="opportunity",
            object_id=opportunity.pk,
            before={k: before[k] for k in changed}, after={k: after[k] for k in changed},
        )  # fmt: skip
    return opportunity


@transaction.atomic
def transition(*, actor, opportunity, to, reason="", today=None):
    """Move an opportunity along the state machine; opening needs a future closing date."""
    today = today or date.today()
    if to not in Opportunity.TRANSITIONS.get(opportunity.status, set()):
        raise RuleViolation(
            "status", f"Cannot go from {opportunity.status} to {to}.", "bad_transition"
        )
    if to == Opportunity.OPEN:
        if opportunity.employer.status == Employer.INACTIVE:
            raise RuleViolation("employer", "Employer is inactive.", "employer_inactive")
        if not opportunity.closing_date or opportunity.closing_date < today:
            raise RuleViolation(
                "closing_date", "Set a closing date in the future before opening.", "closing_date"
            )
    before = opportunity.status
    opportunity.status = to
    opportunity.save(update_fields=["status", "updated_at"])
    audit.record(
        actor=actor, action=f"opportunity.{to}", object_type="opportunity",
        object_id=opportunity.pk, before={"status": before}, after={"status": to}, reason=reason,
    )  # fmt: skip
    return opportunity


def expire_due(*, today=None):
    """Scheduled job: open opportunities past their closing date become expired. Idempotent."""
    today = today or date.today()
    due = Opportunity.objects.filter(status=Opportunity.OPEN, closing_date__lt=today)
    n = 0
    for o in due:
        transition(actor=None, opportunity=o, to=Opportunity.EXPIRED, reason="closing date passed")
        n += 1
    return n


def accepts_referrals(opportunity_id) -> bool:
    """For the referral workflow (T-046): only an open, not-yet-past opportunity takes referrals."""
    return Opportunity.objects.filter(
        pk=opportunity_id, status=Opportunity.OPEN, closing_date__gte=date.today()
    ).exists()


PATTERN_NAMES = {
    "full_time": "full time",
    "part_time": "part time",
    "shift": "shift work",
    "casual": "casual or short contract",
    "remote": "remote or home based",
}


def _typed(requirement, data):
    """Resolve typed ids to rows, drop values that do not belong to the factor, and write the
    plain-English description when none was given."""
    factor = data.get("factor", requirement.factor if requirement else "other")
    keep = OpportunityRequirement.TYPED.get(factor, ())
    out = dict(data)
    for fk, key, kind, label in (
        ("qualification_level", "qualification_level_id", "qualification-levels", "level"),
        ("skill", "skill_id", "skills", "skill"),
    ):
        if key in out and out[key] is not None:
            row = configuration.active_reference(kind, out[key])
            if row is None:
                raise RuleViolation(key, f"Unknown {label}.", "invalid")
            out[fk] = row
        elif key in out:
            out[fk] = None
        out.pop(key, None)
    level = out["qualification_level"] if "qualification_level" in out else (
        requirement.qualification_level if requirement else None
    )  # fmt: skip
    if out.get("min_grade_id"):
        if level is None:
            raise RuleViolation("min_grade_id", "Choose the level first.", "invalid")
        grade = configuration.active_grade(level.pk, out["min_grade_id"])
        if grade is None:
            raise RuleViolation(
                "min_grade_id", "That grade does not belong to this level.", "invalid"
            )
        out["min_grade"] = grade
    elif "min_grade_id" in out or (
        requirement and requirement.min_grade_id and "qualification_level" in out
        and (level is None or requirement.min_grade.level_id != level.pk)
    ):  # fmt: skip
        out["min_grade"] = None  # cleared, or the level changed so the old grade no longer fits
    out.pop("min_grade_id", None)
    if out.get("work_pattern") and out["work_pattern"] not in PATTERN_NAMES:
        raise RuleViolation("work_pattern", "Unknown work pattern.", "invalid")
    for f in (
        "qualification_level",
        "min_grade",
        "skill",
        "min_months",
        "needed_by",
        "work_pattern",
    ):
        if f not in keep and (f in out or (requirement and data.get("factor"))):
            out[f] = "" if f == "work_pattern" else None
    if (requirement is None and not out.get("description")) or (
        "description" in out and not out["description"]
    ):
        probe = {f: out.get(f, getattr(requirement, f, None)) for f in keep}
        if factor == "qualification" and probe.get("qualification_level"):
            name = probe["qualification_level"].name
            grade = probe.get("min_grade")
            out["description"] = (
                f"{name}, grade {grade.name} or above" if grade else f"{name} or higher"
            )
        elif factor == "skill" and probe.get("skill"):
            out["description"] = probe["skill"].name
        elif factor == "experience" and probe.get("min_months") is not None:
            out["description"] = f"At least {probe['min_months']} months of experience"
        elif factor == "availability" and (probe.get("needed_by") or probe.get("work_pattern")):
            bits = []
            if probe.get("needed_by"):
                bits.append(f"can start by {probe['needed_by']}")
            if probe.get("work_pattern"):
                bits.append(PATTERN_NAMES[probe["work_pattern"]])
            out["description"] = "Available: " + ", ".join(bits)
        else:
            raise RuleViolation("description", "Describe the requirement.", "required")
    return out


def _plain(d):
    """Audit-friendly copy: rows and dates become text."""
    return {
        k: (str(v) if v is not None and not isinstance(v, (str, int, bool)) else v)
        for k, v in d.items()
    }


@transaction.atomic
def save_requirement(*, actor, opportunity, data, requirement=None):
    if opportunity.status in (Opportunity.CLOSED, Opportunity.EXPIRED):
        raise RuleViolation("status", "Reopen the opportunity before editing it.", "locked")
    data = _typed(requirement, data)
    skill = data.get("skill")
    if skill is not None:
        twin = opportunity.requirements.filter(skill=skill)
        if requirement is not None:
            twin = twin.exclude(pk=requirement.pk)
        if twin.exists():
            raise RuleViolation("skill_id", f"“{skill.name}” is already required.", "duplicate")
    if requirement is None:
        requirement = OpportunityRequirement.objects.create(opportunity=opportunity, **data)
        action, before = "opportunity.requirement_added", None
    else:
        before = _plain({k: getattr(requirement, k) for k in data})
        for k, v in data.items():
            setattr(requirement, k, v)
        requirement.save()
        action = "opportunity.requirement_updated"
    audit.record(
        actor=actor, action=action, object_type="opportunity", object_id=opportunity.pk,
        before=before, after={"requirement": str(requirement.pk), **_plain(data)},
    )  # fmt: skip
    return requirement


MAX_SKILLS = 50  # a sanity limit on one request, not a product rule


def popular_skills(*, limit=8):
    """Skills opportunities ask for most, with how many opportunities want each. When fewer than
    ``limit`` skills have been asked for yet, the list is topped up from the skills list itself so
    a new installation still has something to start from (those carry ``used`` 0)."""
    from django.db.models import Count

    rows = (
        OpportunityRequirement.objects.filter(skill__isnull=False, skill__active=True)
        .values("skill")
        .annotate(n=Count("opportunity", distinct=True))
        .order_by("-n", "skill__name")[:limit]
    )
    used = {str(r["skill"]): r["n"] for r in rows}
    found = configuration.skills_by_ids(used)
    out = [{**found[k], "used": n} for k, n in used.items() if k in found]
    if len(out) < limit:
        _, more = configuration.search_skills(limit=limit + len(out))
        out += [{**m, "used": 0} for m in more if m["id"] not in used][: limit - len(out)]
    return out


@transaction.atomic
def sync_skill_requirements(*, actor, opportunity, items):
    """Make the opportunity's skill requirements exactly ``items`` (``skill_id``, ``is_mandatory``).

    One call saves the whole picker: skills not listed are removed, new ones added, and a kept
    skill only has its must-have flag updated. A skill repeated in ``items`` counts once."""
    if opportunity.status in (Opportunity.CLOSED, Opportunity.EXPIRED):
        raise RuleViolation("status", "Reopen the opportunity before editing it.", "locked")
    if len(items) > MAX_SKILLS:
        raise RuleViolation("skills", f"Choose at most {MAX_SKILLS} skills.", "too_many")
    want = {}
    for it in items:
        want[str(it["skill_id"])] = bool(it.get("is_mandatory"))
    rows = {}
    for sid in want:
        row = configuration.active_reference("skills", sid)
        if row is None:
            raise RuleViolation("skills", "One of the skills is not in the skills list.", "invalid")
        rows[sid] = row
    have = {str(r.skill_id): r for r in opportunity.requirements.filter(skill__isnull=False)}
    for sid, r in have.items():
        if sid not in want:
            remove_requirement(actor=actor, opportunity=opportunity, requirement=r)
    for sid, mandatory in want.items():
        r = have.get(sid)
        if r is None:
            save_requirement(
                actor=actor, opportunity=opportunity,
                data={"factor": "skill", "skill_id": sid, "is_mandatory": mandatory},
            )  # fmt: skip
        elif r.is_mandatory != mandatory:
            save_requirement(
                actor=actor, opportunity=opportunity,
                data={"is_mandatory": mandatory}, requirement=r,
            )  # fmt: skip
    return list(opportunity.requirements.all())


@transaction.atomic
def remove_requirement(*, actor, opportunity, requirement):
    if opportunity.status in (Opportunity.CLOSED, Opportunity.EXPIRED):
        raise RuleViolation("status", "Reopen the opportunity before editing it.", "locked")
    snap = {"requirement": str(requirement.pk), "description": requirement.description}
    requirement.delete()
    audit.record(
        actor=actor, action="opportunity.requirement_removed", object_type="opportunity",
        object_id=opportunity.pk, before=snap,
    )  # fmt: skip


def opportunity_history(opportunity):
    return audit.history("opportunity", opportunity.pk)


# --- Employer clustering for placement imports (T-087 stage B, doc 15 §8) ---------------------

LEGAL_SUFFIXES = {"ltd", "limited", "co", "company", "inc", "plc", "llc"}


class ClusterError(ValueError):
    """The decision cannot be made or reversed; the message is safe to show."""


def cluster_key(text):
    """Normalised grouping key: case, spacing and punctuation ignored, trailing legal suffixes
    (Ltd, Limited, Co, Company, Inc...) dropped. 'ACME Ltd.' and 'Acme Limited' share a key."""
    words = norm(text).split()
    while len(words) > 1 and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


def build_clusters(names):
    """Group source spellings into review clusters, largest first. Suggestions only: each cluster
    lists existing employers (by name or alias) that share its key. Nothing is changed."""
    spellings = Counter(n.strip() for n in names if n and n.strip())
    groups = {}
    for text, n in spellings.items():
        groups.setdefault(cluster_key(text), []).append((text, n))
    existing = {}
    for e in Employer.objects.filter(archived_at__isnull=True):
        existing.setdefault(cluster_key(e.name), {})[str(e.pk)] = e.name
    for a in EmployerAlias.objects.select_related("employer").filter(
        employer__archived_at__isnull=True
    ):
        existing.setdefault(a.name_key, {})[str(a.employer_id)] = a.employer.name
    clusters = []
    for key, members in groups.items():
        members.sort(key=lambda m: (-m[1], m[0]))
        clusters.append(
            {
                "key": key,
                "spellings": [{"text": t, "count": n} for t, n in members],
                "count": sum(n for _, n in members),
                "suggested": [{"id": i, "name": nm} for i, nm in existing.get(key, {}).items()],
            }
        )
    return sorted(clusters, key=lambda c: (-c["count"], c["key"]))


def resolve_name(text):
    """The employer a source spelling was linked to, or None if no steward has decided it."""
    a = EmployerAlias.objects.filter(source_name=(text or "").strip()).first()
    return a.employer_id if a else None


def _add_alias(employer, text, decision):
    if EmployerAlias.objects.filter(source_name=text).exists():
        raise ClusterError(f"'{text}' is already linked to an employer.")
    return EmployerAlias.objects.create(
        employer=employer, source_name=text, name_key=cluster_key(text), decision=decision
    )


@transaction.atomic
def decide_cluster(*, actor, key, spellings, action, employer_id=None, source=""):
    """Link the spellings to an existing employer, create one employer, or keep them apart (one
    new employer per spelling). Returns the decision."""
    texts = list(dict.fromkeys(s.strip() for s in spellings if s and s.strip()))
    if not texts:
        raise ClusterError("Choose at least one spelling.")
    if action not in {c for c, _ in ClusterDecision.ACTIONS}:
        raise ClusterError(f"Unknown action '{action}'.")
    decision = ClusterDecision.objects.create(
        key=key, action=action, spellings=texts, source=source, decided_by=actor
    )
    created = []
    if action == ClusterDecision.LINK:
        employer = Employer.objects.filter(pk=employer_id, archived_at__isnull=True).first()
        if employer is None:
            raise ClusterError("Choose the existing employer to link to.")
        for t in texts:
            _add_alias(employer, t, decision)
    else:
        groups = [texts] if action == ClusterDecision.CREATE else [[t] for t in texts]
        for group in groups:
            employer = create_employer(actor=actor, data={"name": group[0]}, confirm_duplicate=True)
            created.append(str(employer.pk))
            for t in group:
                _add_alias(employer, t, decision)
    decision.created_employers = created
    decision.save(update_fields=["created_employers"])
    audit.record(
        actor=actor, action="employer.cluster_decided", object_type="cluster_decision",
        object_id=decision.pk,
        after={"action": action, "key": key, "spellings": len(texts), "created": len(created)},
    )  # fmt: skip
    return decision


@transaction.atomic
def reverse_decision(*, actor, decision):
    """Undo a decision: remove its aliases and delete the employers it created. Refused if a
    created employer is already in use (placements or opportunities point at it)."""
    if decision.reversed_at:
        raise ClusterError("This decision was already reversed.")
    decision.aliases.all().delete()
    for emp in Employer.objects.filter(pk__in=decision.created_employers):
        try:
            with transaction.atomic():
                emp.delete()
        except ProtectedError as exc:
            raise ClusterError(
                f"'{emp.name}' is already used by placements or opportunities; unlink those first."
            ) from exc
    decision.reversed_at, decision.reversed_by = timezone.now(), actor
    decision.save(update_fields=["reversed_at", "reversed_by"])
    audit.record(
        actor=actor, action="employer.cluster_reversed", object_type="cluster_decision",
        object_id=decision.pk, after={"key": decision.key},
    )  # fmt: skip
    return decision


def enrich_from_import(*, actor, employer_id, address="", contact_name="", phone="", email=""):
    """Add what a placement file knows about an employer without overwriting anything: the
    address only if blank, a contact only if one with that name does not exist (N-03: phone and
    email are stored as received). Returns what was added, so a rollback can undo exactly it."""
    employer = Employer.objects.get(pk=employer_id)
    undone = {}
    if address.strip() and not employer.address:
        employer.address = address.strip()[:200]
        employer.save(update_fields=["address", "updated_at"])
        undone["address"] = employer.address
    name = contact_name.strip()
    if (
        name
        and (phone.strip() or email.strip())
        and not employer.contacts.filter(name__iexact=name).exists()
    ):
        c = save_contact(
            actor=actor, employer=employer,
            data={"name": name[:150], "phone": phone.strip()[:50], "email": email.strip()[:200],
                  "is_primary": not employer.contacts.exists()},
        )  # fmt: skip
        undone["contact"] = str(c.pk)
    return undone


def undo_enrichment(*, employer_id, undone):
    """Remove what ``enrich_from_import`` added, if it is still as it was."""
    employer = Employer.objects.filter(pk=employer_id).first()
    if employer is None:
        return
    if "contact" in undone:
        EmployerContact.objects.filter(pk=undone["contact"]).delete()
    if "address" in undone and employer.address == undone["address"]:
        employer.address = ""
        employer.save(update_fields=["address", "updated_at"])


@transaction.atomic
def reverse_source(*, actor, source):
    """Reverse every live cluster decision made for one source (e.g. an import batch)."""
    n = 0
    for d in ClusterDecision.objects.filter(source=source, reversed_at__isnull=True):
        reverse_decision(actor=actor, decision=d)
        n += 1
    return n


def compatibility_inputs(opportunity_id):
    """What the compatibility rules read from an opportunity, or None when it does not exist.
    Each requirement carries its typed value; a requirement the rules cannot compare (free text,
    or a category they do not check) has ``structured`` false so the caller can say so."""
    o = Opportunity.objects.filter(pk=opportunity_id).select_related("employer").first()
    if o is None:
        return None
    rows = []
    for r in o.requirements.select_related("qualification_level", "min_grade", "skill"):
        rows.append(
            {
                "id": str(r.pk),
                "factor": r.factor,
                "description": r.description,
                "mandatory": r.is_mandatory,
                "structured": r.factor in r.TYPED and not r.needs_structuring,
                "level_rank": r.qualification_level.rank if r.qualification_level_id else None,
                "min_grade_rank": r.min_grade.rank if r.min_grade_id else None,
                "min_grade": r.min_grade.name if r.min_grade_id else "",
                "skill_id": str(r.skill_id) if r.skill_id else None,
                "min_months": r.min_months,
                "needed_by": r.needed_by.isoformat() if r.needed_by else None,
                "work_pattern": r.work_pattern,
            }
        )
    return {
        "id": str(o.pk),
        "title": o.title,
        "status": o.status,
        "sector_ids": [str(i) for i in o.sectors.values_list("pk", flat=True)],
        "requirements": rows,
    }


# --- for reporting (T-070) -------------------------------------------------------------------


def report_facts() -> dict:
    """Active employers and every live opportunity, as plain facts. An employer or opportunity
    in several counties lists all of them (``county_ids``; empty when none is recorded)."""
    counties = {}
    for owner, county in EmployerCounty.objects.values_list("employer_id", "county_id"):
        counties.setdefault(owner, []).append(county)
    opp_counties = {}
    for owner, county in OpportunityCounty.objects.values_list("opportunity_id", "county_id"):
        opp_counties.setdefault(owner, []).append(county)
    employers = [
        {"id": i, "county_ids": counties.get(i, [])}
        for i in Employer.objects.filter(
            status=Employer.ACTIVE, archived_at__isnull=True
        ).values_list("pk", flat=True)
    ]
    opportunities = [
        {
            "id": i, "status": s, "closing": d, "employer_id": e,
            "county_ids": opp_counties.get(i, []), "created_at": t,
        }
        for i, s, d, e, t in Opportunity.objects.filter(
            archived_at__isnull=True, employer__archived_at__isnull=True
        ).values_list("pk", "status", "closing_date", "employer_id", "created_at")
    ]  # fmt: skip
    return {"employers": employers, "opportunities": opportunities}


def county_names(opportunity) -> str:
    """The opportunity's counties as one readable line (``""`` when none)."""
    return ", ".join(opportunity.counties.order_by("name").values_list("name", flat=True))


def brief_employers(ids) -> dict:
    return {
        e.pk: {"name": e.name, "detail": ", ".join(c.name for c in e.counties.order_by("name"))}
        for e in Employer.objects.filter(pk__in=list(ids)).prefetch_related("counties")
    }


def brief_opportunities(ids) -> dict:
    out = {}
    for o in Opportunity.objects.filter(pk__in=list(ids)).select_related("employer"):
        close = f" · closes {o.closing_date.isoformat()}" if o.closing_date else ""
        out[o.pk] = {
            "name": o.title,
            "detail": f"{o.employer.name} · {o.get_status_display()}{close}",
        }
    return out
