"""Duplicate detection, quarantine queue, merge and unmerge (T-041, DATA-05).

Rules and thresholds are PROPOSALS until D-004 is settled after the data-readiness audit; they
live in ``RULES`` so changing them is one edit. Nothing here merges automatically: ``scan`` only
writes candidate pairs, and ``merge`` runs only when a steward chooses a survivor.
"""

import datetime
import re
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.configuration import services as configuration

from .models import (
    DuplicateCandidate,
    MergeResolution,
    Participant,
    ParticipantContact,
    ParticipantEnrollment,
    ParticipantMerge,
    ParticipantResidence,
    SourceIdentifier,
)

SIMILAR = 0.88  # name similarity treated as "nearly the same"
MAX_SHARED_PHONE = 20  # a phone shared by more people than this is an office or household line
RULES = {  # code -> (score, description)
    "name_phone": (0.95, "Same name and the same phone number"),
    "similar_name_phone": (0.85, "Nearly the same name and the same phone number"),
    "name_project": (0.80, "Same name in the same project, different enrollment number"),
}
MERGE_FIELDS = (
    "full_name_source", "given_name", "family_name", "other_names", "gender",
    "date_of_birth", "age_at_source", "age_basis_date", "origin_county_id", "status",
)  # fmt: skip
DATE_FIELDS = {"date_of_birth", "age_basis_date"}


class DuplicateFailure(Exception):
    def __init__(self, message, field="non_field_errors"):
        super().__init__(message)
        self.message, self.field = message, field


def _phone_key(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-9:] if len(digits) >= 9 else ""  # +254 700 000 000 and 0700000000 agree


def _ordered(a, b):
    return (a, b) if str(a) < str(b) else (b, a)


# --- detection ---------------------------------------------------------------


def find_pairs(only=None) -> dict:
    """Candidate pairs as {(id_a, id_b): (score, [rule codes])}. ``only`` limits it to pairs that
    involve those participant ids (used right after an import). Indexes are built once, so a
    full scan is a few queries plus the pairwise checks inside each small block."""
    live = Participant.objects.filter(merged_into__isnull=True)
    names = {
        pid: configuration.normalise(n) for pid, n in live.values_list("id", "full_name_source")
    }
    phones = defaultdict(set)
    for pid, value in ParticipantContact.objects.filter(
        kind="phone", participant__merged_into__isnull=True
    ).values_list("participant_id", "value"):
        if key := _phone_key(value):
            phones[key].add(pid)
    projects = defaultdict(set)
    numbers = defaultdict(set)
    for pid, prog, no in ParticipantEnrollment.objects.filter(
        participant__merged_into__isnull=True
    ).values_list("participant_id", "project_id", "source_enrollment_no"):
        projects[pid].add(prog)
        numbers[pid].add((prog, no))
    by_name = defaultdict(list)
    for pid, n in names.items():
        if n:
            by_name[n].append(pid)

    found: dict = {}

    def add(a, b, rule):
        key = _ordered(a, b)
        score = RULES[rule][0]
        if key not in found:
            found[key] = (score, [rule])
        else:
            found[key] = (max(score, found[key][0]), [*found[key][1], rule])

    for ids in phones.values():
        if 1 < len(ids) <= MAX_SHARED_PHONE:
            for a, b in combinations(sorted(ids, key=str), 2):
                ratio = SequenceMatcher(None, names[a], names[b]).ratio()
                if ratio == 1:
                    add(a, b, "name_phone")
                elif ratio >= SIMILAR:
                    add(a, b, "similar_name_phone")
    for ids in by_name.values():
        for a, b in combinations(sorted(ids, key=str), 2):
            shared = projects[a] & projects[b]
            if shared and not (numbers[a] & numbers[b]):
                add(a, b, "name_project")
    if only is not None:
        only = {str(i) for i in only}  # accept UUIDs or their string form
        found = {k: v for k, v in found.items() if str(k[0]) in only or str(k[1]) in only}
    return found


def scan(*, actor=None, only=None) -> dict:
    """Record candidate pairs for the steward queue. Safe to repeat: a pair that was dismissed
    or merged is not reopened."""
    pairs = find_pairs(only)
    new = 0
    with transaction.atomic():
        for (a, b), (score, reasons) in pairs.items():
            cand, created = DuplicateCandidate.objects.get_or_create(
                participant_a_id=a,
                participant_b_id=b,
                defaults={"score": score, "reasons": reasons},
            )
            new += created
            if not created and cand.status == DuplicateCandidate.OPEN:
                cand.score, cand.reasons = score, reasons
                cand.save(update_fields=["score", "reasons"])
        result = {"pairs": len(pairs), "new": new}
        if actor is not None:
            audit.record(
                actor=actor,
                action="duplicates.scanned",
                object_type="duplicate_scan",
                object_id=actor.pk if hasattr(actor, "pk") else 0,
                after=result,
            )
    return result


# --- queue decisions -----------------------------------------------------------


def _open_candidate(candidate):
    if candidate.status != DuplicateCandidate.OPEN:
        raise DuplicateFailure("This pair has already been decided.", "status")


@transaction.atomic
def dismiss(*, actor, candidate, note=""):
    candidate = DuplicateCandidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.status != DuplicateCandidate.PENDING:  # a pending merge may still be dropped
        _open_candidate(candidate)
    candidate.status = DuplicateCandidate.DISMISSED
    candidate.decided_by, candidate.decided_at = actor, timezone.now()
    candidate.note = note[:500]
    candidate.save()
    audit.record(
        actor=actor,
        action="duplicate.dismissed",
        object_type="duplicate_candidate",
        object_id=candidate.pk,
        reason=note,
    )
    return candidate


# --- merge / unmerge -----------------------------------------------------------


def _val(v):
    return None if v is None else str(v)


def _parse(field, v):
    if v is not None and field in DATE_FIELDS:
        return datetime.date.fromisoformat(v)
    return v


@transaction.atomic
def _profile_models(ids_by_kind):
    from .models import (
        ParticipantExperience,
        ParticipantQualification,
        ParticipantReadiness,
        ParticipantSkill,
    )

    names = {
        "qualifications": ParticipantQualification,
        "skills": ParticipantSkill,
        "experience": ParticipantExperience,
        "readiness": ParticipantReadiness,
    }
    return [(names[k], v) for k, v in ids_by_kind.items() if k in names]


def _move_profile(absorbed, survivor):
    """Move the absorbed record's capability facts to the survivor. A skill the survivor already
    has stays behind, and so does the readiness row if the survivor has one (their own wins)."""
    moved = {"qualifications": [], "skills": [], "experience": [], "readiness": []}
    have = set(survivor.skills.values_list("skill_id", flat=True))
    for q in absorbed.qualifications.all():
        moved["qualifications"].append(str(q.pk))
        q.participant = survivor
        q.save(update_fields=["participant"])
    for s in absorbed.skills.all():
        if s.skill_id in have:
            continue
        moved["skills"].append(str(s.pk))
        s.participant = survivor
        s.save(update_fields=["participant"])
    for e in absorbed.experience.all():
        moved["experience"].append(str(e.pk))
        e.participant = survivor
        e.save(update_fields=["participant"])
    ready = getattr(absorbed, "readiness", None)
    if ready is not None and not hasattr(survivor, "readiness"):
        moved["readiness"].append(str(ready.pk))
        ready.participant = survivor
        ready.save(update_fields=["participant"])
    return moved


# --- merge review: what is consolidated, what needs a choice, what blocks (NEW-077) -----------

# Other modules add their own critical checks (running placements, referrals, portal accounts):
# participants may not import them (doc 04), so the case-management coordinator registers them at
# start-up. Each is ``check(survivor, absorbed) -> list of conflict dicts`` (see ``_conflict``).
CHECKS: list = []


def add_check(fn):
    if fn not in CHECKS:
        CHECKS.append(fn)
    return fn


def conflict(code, message, *, items=(), actions=(), hint=""):
    """One critical conflict. ``actions`` are the resolutions an officer may record from the
    merge screen; with none, ``hint`` says where to fix it first. Items carry ids, not details."""
    return {"code": code, "message": message, "items": list(items), "actions": list(actions),
            "hint": hint}  # fmt: skip


BLANK = {None, "", "unknown"}  # gender/status "unknown" carry no information
FIELD_LABELS = {
    "full_name_source": "Full name", "given_name": "Given name", "family_name": "Family name",
    "other_names": "Other names", "gender": "Gender", "date_of_birth": "Date of birth",
    "age_at_source": "Age", "age_basis_date": "Age recorded on", "origin_county_id": "County",
    "status": "Training status",
}  # fmt: skip


def _shown(p, field):
    if field == "origin_county_id":
        return p.origin_county.name if p.origin_county_id else None
    return _val(getattr(p, field))


def _pair(candidate, survivor_id, *, lock=False):
    pair = {str(candidate.participant_a_id), str(candidate.participant_b_id)}
    if str(survivor_id) not in pair:
        raise DuplicateFailure("The survivor must be one of the two records.", "survivor")
    qs = Participant.objects.select_for_update() if lock else Participant.objects
    survivor = qs.get(pk=survivor_id)
    absorbed = qs.get(pk=(pair - {str(survivor_id)}).pop())
    if survivor.merged_into_id or absorbed.merged_into_id:
        raise DuplicateFailure("One of these records has already been merged.", "status")
    return survivor, absorbed


def _fields(survivor, absorbed, choices=None):
    """Per field: both values, whether it is a real conflict (both filled and different) and
    the value kept. A gap on one side is filled from the other automatically; a real conflict
    must be chosen by the steward (``choices``), never guessed."""
    choices = choices or {}
    out = []
    for f in MERGE_FIELDS:
        s, m = getattr(survivor, f), getattr(absorbed, f)
        clash = s not in BLANK and m not in BLANK and s != m
        if f in choices:
            keep = choices[f]
        elif clash:
            keep = None  # waiting for the steward
        else:
            keep = "merged" if s in BLANK and m not in BLANK else "survivor"
        out.append({
            "field": f, "label": FIELD_LABELS[f], "survivor": _shown(survivor, f),
            "merged": _shown(absorbed, f), "conflict": clash, "keep": keep,
        })  # fmt: skip
    return out


def _critical(survivor, absorbed):
    found = []
    clash = set(survivor.enrollments.values_list("cohort_course_id", flat=True)) & set(
        absorbed.enrollments.values_list("cohort_course_id", flat=True)
    )
    if clash:
        found.append(conflict(
            "same_course_offering",
            "Both records are enrolled in the same course offering.",
            hint="Withdraw or correct one of the two enrollments on the youth's record first.",
        ))  # fmt: skip
    for check in CHECKS:
        found.extend(check(survivor, absorbed))
    return found


def review(*, candidate, survivor_id) -> dict:
    """What merging into ``survivor_id`` would do, before anything is changed."""
    survivor, absorbed = _pair(candidate, survivor_id)
    return {
        "survivor": str(survivor.pk),
        "merged": str(absorbed.pk),
        "fields": _fields(survivor, absorbed),
        "critical": _critical(survivor, absorbed),
    }


def _check_choices(fields):
    fields = fields or {}
    bad = sorted(set(fields) - set(MERGE_FIELDS))
    if bad or any(v not in ("survivor", "merged") for v in fields.values()):
        raise DuplicateFailure(f"Unknown field choice: {', '.join(bad) or 'value'}.", "fields")
    return fields


@transaction.atomic
def merge(*, actor, candidate, survivor_id, fields=None, reason):
    """The steward asks to fold one record into the other: they pick the survivor and, for each
    real conflict, whose value to keep. If a critical conflict remains (two running placements,
    the same course offering, ...) nothing is moved: the pair is saved as pending resolution and
    returned with ``conflicts``. Otherwise the merge runs and its ``ParticipantMerge`` is
    returned."""
    candidate = DuplicateCandidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.status not in (DuplicateCandidate.OPEN, DuplicateCandidate.PENDING):
        raise DuplicateFailure("This pair has already been decided.", "status")
    if not reason.strip():
        raise DuplicateFailure("Give a reason.", "reason")
    fields = _check_choices(fields)
    survivor, absorbed = _pair(candidate, survivor_id, lock=True)
    plan = _fields(survivor, absorbed, fields)
    open_fields = [f["label"] for f in plan if f["keep"] is None]
    if open_fields:
        raise DuplicateFailure(
            f"Choose which value to keep for: {', '.join(open_fields)}.", "fields"
        )
    found = _critical(survivor, absorbed)
    if found:
        candidate.status = DuplicateCandidate.PENDING
        candidate.plan = {
            "survivor": str(survivor.pk), "fields": fields, "reason": reason[:500],
            "saved_by": actor.pk if actor else None, "saved_at": timezone.now().isoformat(),
        }  # fmt: skip
        candidate.save(update_fields=["status", "plan"])
        audit.record(
            actor=actor, action="duplicate.merge_pending", object_type="duplicate_candidate",
            object_id=candidate.pk, after={"survivor": str(survivor.pk),
            "merged": str(absorbed.pk), "conflicts": [c["code"] for c in found]}, reason=reason,
        )  # fmt: skip
        candidate.conflicts = found
        return candidate
    return _execute(actor, candidate, survivor, absorbed, plan, reason, fields)


@transaction.atomic
def resolve(*, actor, candidate, conflict_code, action, reason, detail=None):
    """Record how an authorised officer resolved one critical conflict on a pending merge.
    The module that owns the data (e.g. placements) does the change itself, in the same
    transaction; this keeps who, when, why and what."""
    candidate = DuplicateCandidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.status != DuplicateCandidate.PENDING:
        raise DuplicateFailure(
            "Only a merge pending resolution has conflicts to resolve.", "status"
        )
    if not (reason or "").strip():
        raise DuplicateFailure("Give a reason.", "reason")
    row = MergeResolution.objects.create(
        candidate=candidate, conflict=conflict_code, action=action, detail=detail or {},
        reason=reason.strip()[:500], decided_by=actor,
    )  # fmt: skip
    audit.record(
        actor=actor, action="duplicate.conflict_resolved", object_type="duplicate_candidate",
        object_id=candidate.pk, after={"conflict": conflict_code, "action": action,
        **(detail or {})}, reason=reason,
    )  # fmt: skip
    return row


@transaction.atomic
def complete(*, actor, candidate):
    """Finish a pending merge with the plan the steward saved, once nothing critical is left."""
    candidate = DuplicateCandidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.status != DuplicateCandidate.PENDING:
        raise DuplicateFailure("This merge is not pending resolution.", "status")
    plan = candidate.plan
    survivor, absorbed = _pair(candidate, plan["survivor"], lock=True)
    fields = _check_choices(plan.get("fields"))
    chosen = _fields(survivor, absorbed, fields)
    if open_fields := [f["label"] for f in chosen if f["keep"] is None]:
        raise DuplicateFailure(
            f"A value changed since the merge was saved. Choose again for: "
            f"{', '.join(open_fields)}.", "fields",
        )  # fmt: skip
    if found := _critical(survivor, absorbed):
        raise DuplicateFailure(
            "Resolve these first: " + "; ".join(c["message"] for c in found), "conflicts"
        )
    return _execute(actor, candidate, survivor, absorbed, chosen, plan["reason"], fields)


# --- the merge itself ----------------------------------------------------------------------

# Handled one by one below (their rules differ); every other link to a youth is moved by
# ``_move_linked``, generically, so a module added later is not forgotten.
HANDLED = {
    "participants.participantenrollment", "participants.participantcontact",
    "participants.participantresidence", "participants.sourceidentifier",
    "participants.participantqualification", "participants.participantskill",
    "participants.participantexperience", "participants.participantreadiness",
    "participants.profileverification",
    # merge bookkeeping is history, never re-pointed: the pair and earlier merges keep their ids
    "participants.duplicatecandidate", "participants.participantmerge",
}  # fmt: skip


def _move_linked(absorbed, survivor, moved_facts):
    """Move the absorbed record's remaining linked rows (referrals, interventions, documents,
    the portal account, ...) to the survivor. Only the youth link changes: authors, dates and
    content stay. A row the survivor cannot take (it already has its own photo, say) stays on
    the merged record, kept and listed. Verifications follow the facts they check."""
    out = {}
    # include_hidden: links declared with related_name="+" (referrals, ...) are not in
    # ``related_objects`` but must move too.
    rels = [
        r for r in Participant._meta.get_fields(include_hidden=True)
        if r.auto_created and not r.concrete and (r.one_to_many or r.one_to_one)
    ]  # fmt: skip
    for rel in rels:
        model, field = rel.related_model, rel.field
        label = model._meta.label_lower
        if label in HANDLED or model is Participant or not field.concrete:
            continue
        moved, kept = [], []
        for pk in model._base_manager.filter(**{field.name: absorbed}).values_list("pk", flat=True):
            try:
                with transaction.atomic():
                    model._base_manager.filter(pk=pk).update(**{field.name: survivor})
                moved.append(str(pk))
            except IntegrityError:
                kept.append(str(pk))
        if moved or kept:
            out[label] = {"field": field.name, "moved": moved, "kept": kept}
            if label.split(".")[0] == "participants":
                moved_facts.update(moved)
    from .models import ProfileVerification

    ver = ProfileVerification.objects.filter(participant=absorbed, fact_id__in=moved_facts)
    ids = [str(i) for i in ver.values_list("pk", flat=True)]
    ver.update(participant=survivor)
    if ids:
        out["participants.profileverification"] = {"field": "participant", "moved": ids,
                                                   "kept": []}  # fmt: skip
    return out


def _execute(actor, candidate, survivor, absorbed, plan, reason, fields):
    """Run a merge whose plan has no open question and no critical conflict. Children are
    re-pointed; the absorbed row stays (hidden, marked merged, linked to the survivor) so the
    merge can be undone and both ids stay traceable."""
    snap = {
        "survivor_before": {f: _val(getattr(survivor, f)) for f in MERGE_FIELDS},
        "enrollments": [str(i) for i in absorbed.enrollments.values_list("id", flat=True)],
        "identifiers": [str(i) for i in absorbed.source_identifiers.values_list("id", flat=True)],
        "contacts": [],
        "residences": [],
        "profile": _move_profile(absorbed, survivor),
    }
    kept_from_merged = [f["field"] for f in plan if f["keep"] == "merged"]
    for f in kept_from_merged:
        setattr(survivor, f, getattr(absorbed, f))
    survivor.save()

    absorbed.enrollments.update(participant=survivor)  # placements follow their enrollment
    SourceIdentifier.objects.filter(participant=absorbed).update(participant=survivor)
    for c in list(absorbed.contacts.all()):
        snap["contacts"].append({"id": str(c.pk), "is_primary": c.is_primary})
        c.participant = survivor
        if c.is_primary and survivor.contacts.filter(kind=c.kind, is_primary=True).exists():
            c.is_primary = False  # the survivor's own primary wins
        c.save()
    for r in list(absorbed.residences.all()):
        snap["residences"].append({"id": str(r.pk), "valid_to": _val(r.valid_to)})
        r.participant = survivor
        if r.valid_to is None and survivor.residences.filter(valid_to__isnull=True).exists():
            r.valid_to = timezone.localdate()  # only one current residence is allowed
        r.save()
    facts = {i for ids in snap["profile"].values() for i in ids}
    snap["linked"] = _move_linked(absorbed, survivor, facts)

    absorbed.merged_into = survivor
    absorbed.save(update_fields=["merged_into", "updated_at"])
    resolutions = [str(r) for r in candidate.resolutions.values_list("pk", flat=True)]
    record = ParticipantMerge.objects.create(
        survivor=survivor,
        absorbed=absorbed,
        candidate=candidate,
        snapshot=snap,
        reason=reason[:500],
        created_by=actor,
    )
    candidate.status = DuplicateCandidate.MERGED
    candidate.decided_by, candidate.decided_at = actor, timezone.now()
    candidate.save()
    trail = {"merge": str(record.pk), "survivor": str(survivor.pk), "merged": str(absorbed.pk),
             "fields": kept_from_merged, "resolutions": resolutions}  # fmt: skip
    audit.record(
        actor=actor, action="participant.merged", object_type="participant",
        object_id=survivor.pk, before={"absorbed": str(absorbed.pk)}, after=trail, reason=reason,
    )  # fmt: skip
    audit.record(
        actor=actor, action="participant.merged_into", object_type="participant",
        object_id=absorbed.pk, after=trail, reason=reason,
    )  # fmt: skip
    return record


@transaction.atomic
def unmerge(*, actor, merge_record, reason):
    record = ParticipantMerge.objects.select_for_update().get(pk=merge_record.pk)
    if record.undone_at:
        raise DuplicateFailure("This merge was already undone.", "status")
    if not reason.strip():
        raise DuplicateFailure("Give a reason.", "reason")
    survivor, absorbed = record.survivor, record.absorbed
    if survivor.merged_into_id:
        raise DuplicateFailure(
            "The surviving record was itself merged later. Undo that merge first.", "status"
        )
    snap = record.snapshot
    for f, v in snap["survivor_before"].items():
        setattr(survivor, f, _parse(f, v))
    survivor.save()

    ParticipantEnrollment.objects.filter(pk__in=snap["enrollments"], participant=survivor).update(
        participant=absorbed
    )
    SourceIdentifier.objects.filter(pk__in=snap["identifiers"], participant=survivor).update(
        participant=absorbed
    )
    for c in snap["contacts"]:
        ParticipantContact.objects.filter(pk=c["id"], participant=survivor).update(
            participant=absorbed
        )
        ParticipantContact.objects.filter(pk=c["id"]).update(is_primary=c["is_primary"])
    for model, ids in _profile_models(snap.get("profile", {})):
        model.objects.filter(pk__in=ids, participant=survivor).update(participant=absorbed)
    from django.apps import apps

    for label, row in snap.get("linked", {}).items():
        model = apps.get_model(label)
        model._base_manager.filter(pk__in=row["moved"], **{row["field"]: survivor}).update(
            **{row["field"]: absorbed}
        )
    for r in snap["residences"]:
        ParticipantResidence.objects.filter(pk=r["id"], participant=survivor).update(
            participant=absorbed,
            valid_to=_parse("valid_to", r["valid_to"]) if r["valid_to"] else None,
        )
    absorbed.merged_into = None
    absorbed.save(update_fields=["merged_into", "updated_at"])
    # A placement marked "recorded twice" while resolving stays so: that was a person's decision
    # about the placements themselves, not part of the merge.
    record.undone_by, record.undone_at, record.undo_reason = actor, timezone.now(), reason[:500]
    record.save()
    if record.candidate_id:
        DuplicateCandidate.objects.filter(pk=record.candidate_id).update(
            status=DuplicateCandidate.OPEN, decided_by=None, decided_at=None
        )
    audit.record(
        actor=actor,
        action="participant.unmerged",
        object_type="participant",
        object_id=survivor.pk,
        before={"merge": str(record.pk)},
        after={"restored": str(absorbed.pk)},
        reason=reason,
    )
    return record


# --- helpers for the import pipeline (T-041 quarantine, T-042 reconciliation) -----------------


def quarantined(ids) -> set:
    """Of these participant ids, those in an open or pending duplicate pair (held for a steward)."""
    ids = {str(i) for i in ids}
    out = set()
    held = (DuplicateCandidate.OPEN, DuplicateCandidate.PENDING)
    for a, b in DuplicateCandidate.objects.filter(status__in=held).values_list(
        "participant_a_id", "participant_b_id"
    ):
        out |= {str(a), str(b)} & ids
    return out


def involved_in_merge(ids) -> bool:
    """True if any of these participants was merged into, or absorbed by, another record."""
    ids = list(ids)
    return (
        ParticipantMerge.objects.filter(undone_at__isnull=True, survivor_id__in=ids).exists()
        or ParticipantMerge.objects.filter(undone_at__isnull=True, absorbed_id__in=ids).exists()
    )


def cohort_counts(ids) -> dict:
    """{cohort code: distinct participants among ``ids`` enrolled in it}. The control total the
    reconciliation report compares with the source file."""
    out = defaultdict(set)
    for pid, code in ParticipantEnrollment.objects.filter(participant_id__in=list(ids)).values_list(
        "participant_id", "cohort_course__cohort__code"
    ):
        out[code.upper()].add(pid)
    return {k: len(v) for k, v in out.items()}


def get_candidate(pk):
    """The duplicate pair with this id, or None: for modules that may not import the model."""
    return DuplicateCandidate.objects.filter(pk=pk).first()
