"""Finding disability answers in imported sheets (NEW-042, D-082).

Two steps, and the first copies nothing:

1. ``key_report`` lists the extra column names found on imported enrolments that look like they
   might hold disability, with how many rows have each. Names and counts only: no value is read
   into the report.
2. ``apply_mapping`` copies answers for ONE column that a person has chosen, using the yes/no
   words they listed. It does nothing unless ``approved=True`` (a dry run says what would change),
   needs the disability flag on, never overwrites an answer someone already recorded, and marks
   what it writes with the source "import". A cell whose text is in neither list is left alone and
   counted as "unmatched": nothing is guessed.
"""

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.configuration import services as configuration

from . import disability
from .models import Participant, ParticipantEnrollment

HINTS = ("disab", "pwd", "handicap", "impair", "special need", "wheelchair", "blind", "deaf")
IMPORTED = "participant.disability_imported"


class MappingError(ValueError):
    pass


def _norm(text) -> str:
    return " ".join(str(text).strip().lower().split())


def _has_value(v) -> bool:
    return v is not None and str(v).strip() != ""


def key_report() -> list[dict]:
    """``[{key, rows, candidate}]`` for every extra column, with the number of enrolments that
    filled it in. ``candidate`` says the NAME looks disability-related. Values are never read
    into the result."""
    counts: dict[str, int] = {}
    for extra in ParticipantEnrollment.objects.exclude(extra={}).values_list("extra", flat=True):
        for key, value in (extra or {}).items():
            if _has_value(value):
                counts[key] = counts.get(key, 0) + 1
    return sorted(
        (
            {"key": k, "rows": n, "candidate": any(h in _norm(k) for h in HINTS)}
            for k, n in counts.items()
        ),
        key=lambda r: (not r["candidate"], r["key"]),
    )


@transaction.atomic
def apply_mapping(*, actor, key, yes_words, no_words, approved=False) -> dict:
    """Copy answers from one extra column. Returns counts only."""
    yes, no = {_norm(w) for w in yes_words}, {_norm(w) for w in no_words}
    if not key or not yes or not no or yes & no:
        raise MappingError("Give the column and separate yes and no words.")
    if approved and not configuration.is_enabled(disability.FLAG):
        raise MappingError("Switch the disability feature on before importing answers.")
    result = {"key": key, "would_set": 0, "unmatched": 0, "already_recorded": 0, "set": 0}
    seen = set()
    rows = ParticipantEnrollment.objects.exclude(extra={}).values_list("participant_id", "extra")
    for pid, extra in rows:
        value = (extra or {}).get(key)
        if not _has_value(value) or pid in seen:
            continue
        seen.add(pid)
        word = _norm(value)
        answer = "yes" if word in yes else "no" if word in no else None
        if answer is None:
            result["unmatched"] += 1
            continue
        p = Participant.objects.get(pk=pid)
        if p.disability != Participant.DISABILITY_NOT_RECORDED:
            result["already_recorded"] += 1
            continue
        result["would_set"] += 1
        if approved:
            # The imported text is not kept as a description: only the yes / no answer.
            Participant.objects.filter(pk=pid).update(
                disability=answer, disability_recorded_at=timezone.now(), disability_source="import"
            )
            result["set"] += 1
    if approved:
        audit.record(
            actor=actor, action=IMPORTED, object_type="participant", object_id="import",
            after={"column": key, "set": result["set"], "unmatched": result["unmatched"]},
        )  # fmt: skip
    return result
