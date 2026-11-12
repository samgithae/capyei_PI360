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

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.configuration import services as configuration

from .models import (
    DuplicateCandidate,
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
    "name_programme": (0.80, "Same name in the same programme, different enrollment number"),
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
    programmes = defaultdict(set)
    numbers = defaultdict(set)
    for pid, prog, no in ParticipantEnrollment.objects.filter(
        participant__merged_into__isnull=True
    ).values_list("participant_id", "programme_id", "source_enrollment_no"):
        programmes[pid].add(prog)
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
            shared = programmes[a] & programmes[b]
            if shared and not (numbers[a] & numbers[b]):
                add(a, b, "name_programme")
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


def merge(*, actor, candidate, survivor_id, fields=None, reason):
    """Fold one record into the other. The steward picks the survivor and, per field, whose value
    to keep. Children are re-pointed; the absorbed row stays (hidden) so this can be undone."""
    candidate = DuplicateCandidate.objects.select_for_update().get(pk=candidate.pk)
    _open_candidate(candidate)
    if not reason.strip():
        raise DuplicateFailure("Give a reason.", "reason")
    pair = {str(candidate.participant_a_id), str(candidate.participant_b_id)}
    if str(survivor_id) not in pair:
        raise DuplicateFailure("The survivor must be one of the two records.", "survivor")
    survivor = Participant.objects.select_for_update().get(pk=survivor_id)
    absorbed = Participant.objects.select_for_update().get(pk=(pair - {str(survivor_id)}).pop())
    if survivor.merged_into_id or absorbed.merged_into_id:
        raise DuplicateFailure("One of these records has already been merged.", "status")
    fields = fields or {}
    bad = sorted(set(fields) - set(MERGE_FIELDS))
    if bad or any(v not in ("survivor", "merged") for v in fields.values()):
        raise DuplicateFailure(f"Unknown field choice: {', '.join(bad) or 'value'}.", "fields")
    clash = set(survivor.enrollments.values_list("cohort_course_id", flat=True)) & set(
        absorbed.enrollments.values_list("cohort_course_id", flat=True)
    )
    if clash:
        raise DuplicateFailure(
            "Both records are enrolled in the same course offering. Resolve that enrollment first.",
            "enrollments",
        )

    snap = {
        "survivor_before": {f: _val(getattr(survivor, f)) for f in MERGE_FIELDS},
        "enrollments": [str(i) for i in absorbed.enrollments.values_list("id", flat=True)],
        "identifiers": [str(i) for i in absorbed.source_identifiers.values_list("id", flat=True)],
        "contacts": [],
        "residences": [],
        "profile": _move_profile(absorbed, survivor),
    }
    for f, who in fields.items():
        if who == "merged":
            setattr(survivor, f, getattr(absorbed, f))
    survivor.save()

    absorbed.enrollments.update(participant=survivor)
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

    absorbed.merged_into = survivor
    absorbed.save(update_fields=["merged_into", "updated_at"])
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
    audit.record(
        actor=actor,
        action="participant.merged",
        object_type="participant",
        object_id=survivor.pk,
        before={"absorbed": str(absorbed.pk)},
        after={"merge": str(record.pk), "fields": fields},
        reason=reason,
    )
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
    for r in snap["residences"]:
        ParticipantResidence.objects.filter(pk=r["id"], participant=survivor).update(
            participant=absorbed,
            valid_to=_parse("valid_to", r["valid_to"]) if r["valid_to"] else None,
        )
    absorbed.merged_into = None
    absorbed.save(update_fields=["merged_into", "updated_at"])
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
    """Of these participant ids, those sitting in an open duplicate pair (held for a steward)."""
    ids = {str(i) for i in ids}
    out = set()
    for a, b in DuplicateCandidate.objects.filter(status=DuplicateCandidate.OPEN).values_list(
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
