"""Search and duplicate warnings (T-055, FR-37).

Two jobs, both portable (they run the same on SQLite in tests and PostgreSQL in production; a
``pg_trgm`` index can speed them up later without changing what they return):

* ``similar_to``: before a youth is saved, who already looks like them? Used by the Add youth
  wizard. Never blocks saving; a steward or officer decides.
* ``search``: the directory search box. Every word must appear (in any order), source IDs and
  enrollment numbers count, and when nothing matches it falls back to near-spellings so a typo
  still finds the person.

The thresholds are proposals (D-004 settles the steward queue's rules in ``duplicates.RULES``;
these are warnings, not queue entries, so they are deliberately a little more generous).
"""

from difflib import SequenceMatcher

from django.db.models import Q

from apps.configuration import services as configuration

from .duplicates import SIMILAR, _phone_key
from .models import ParticipantContact

NAME_WITH_PHONE = 0.6  # shares a name part and the phone number
NAME_WITH_BIRTHDATE = 0.7  # nearly the same name and the same date of birth
TYPO = 0.8  # one search word versus one word of a name
MAX_FUZZY_SCOPE = 20000  # names compared in the typo fallback; bigger scopes skip it

REASONS = {
    "same_name": "Same name",
    "same_words": "Same name words in a different order",
    "similar_name": "Almost the same name",
    "same_phone": "Same phone number and a similar name",
    "same_birthdate": "Same date of birth and a similar name",
}
_ORDER = ["same_name", "same_words", "similar_name", "same_phone", "same_birthdate"]


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    m = SequenceMatcher(None, a, b)
    if m.real_quick_ratio() < 0.5 or m.quick_ratio() < 0.5:
        return 0.0
    return m.ratio()


def _words(norm_name: str) -> str:
    """The name's words sorted, so 'Kamau John' and 'John Kamau' compare equal."""
    return " ".join(sorted(norm_name.split()))


def similar_to(*, name: str, scope, phone: str = "", birth_date=None, limit: int = 5) -> list[dict]:
    """People in ``scope`` (a Participant queryset the caller may see) who look like this one.

    Each result carries why it matched. The matched phone number or birth date is never
    returned, only the fact that it agrees."""
    target = configuration.normalise(name)
    if len(target) < 3:
        return []
    key = _phone_key(phone)
    phone_ids: set = set()
    if key:
        for pid, value in ParticipantContact.objects.filter(
            kind="phone", participant__in=scope.values("pk")
        ).values_list("participant_id", "value"):
            if _phone_key(value) == key:
                phone_ids.add(pid)
    target_words = _words(target)
    found = []
    for pid, full, status, dob in scope.filter(merged_into__isnull=True).values_list(
        "pk", "full_name_source", "status", "date_of_birth"
    ):
        n = configuration.normalise(full)
        ratio = max(_ratio(target, n), _ratio(target_words, _words(n)))
        reasons = []
        if n == target:
            reasons.append("same_name")
        elif _words(n) == target_words:
            reasons.append("same_words")
        elif ratio >= SIMILAR:
            reasons.append("similar_name")
        if pid in phone_ids and ratio >= NAME_WITH_PHONE:
            reasons.append("same_phone")
        if birth_date and dob == birth_date and ratio >= NAME_WITH_BIRTHDATE:
            reasons.append("same_birthdate")
        if reasons:
            found.append((pid, full, status, ratio, reasons))
    found.sort(key=lambda r: (-len(r[4]), -r[3], r[1], str(r[0])))
    found = found[:limit]
    context = _context(scope, [f[0] for f in found])
    return [
        {
            "id": str(pid),
            "name": full,
            "status": status,
            "county": context.get(pid, {}).get("county", ""),
            "projects": context.get(pid, {}).get("projects", []),
            "reasons": [{"code": r, "text": REASONS[r]} for r in sorted(rs, key=_ORDER.index)],
        }
        for pid, full, status, _ratio_, rs in found
    ]


def _context(scope, ids) -> dict:
    """County and projects for a few matches, so the person deciding can tell them apart."""
    rows = (
        scope.filter(pk__in=ids)
        .select_related("origin_county")
        .prefetch_related("enrollments__project")
    )
    return {
        p.pk: {
            "county": p.origin_county.name if p.origin_county_id else "",
            "projects": sorted({e.project.name for e in p.enrollments.all()}),
        }
        for p in rows
    }


# --- directory search ---------------------------------------------------------------------


def _exact(qs, text: str):
    words = configuration.normalise(text).split()
    if not words:
        return qs
    by_name = Q()
    for w in words:
        by_name &= Q(full_name_source__icontains=w)
    by_number = Q(enrollments__source_enrollment_no__icontains=text.strip()) | Q(
        source_identifiers__identifier__icontains=text.strip()
    )
    return qs.filter(by_name | by_number).distinct()


def search(qs, text: str):
    """Filter ``qs`` by what was typed. Returns ``(queryset, fuzzy)``; ``fuzzy`` is True when
    nothing matched exactly and the results are near-spellings instead."""
    text = text.strip()
    if not text:
        return qs, False
    hits = _exact(qs, text)
    if hits.exists() or len(text) < 3:
        return hits, False
    words = configuration.normalise(text).split()
    if not words or qs.count() > MAX_FUZZY_SCOPE:
        return hits, False
    close = []
    for pid, full in qs.values_list("pk", "full_name_source"):
        parts = configuration.normalise(full).split()
        if parts and all(any(_ratio(w, p) >= TYPO for p in parts) for w in words):
            close.append(pid)
    return qs.filter(pk__in=close), bool(close)
