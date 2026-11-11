"""The fixed set of comparison operators (doc 07 §2.1). A new operator needs a code release
(ADR-003); rule versions can only pick from this registry.

Every operator is tri-state (doc 07 §2.3): it returns pass, fail or unknown. A missing value,
an unset threshold or a value it cannot compare gives **unknown**, never a silent fail."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from math import asin, cos, radians, sin, sqrt

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"


@dataclass(frozen=True)
class Check:
    """Result of one comparison. ``score`` is 1 for pass, 0 for fail, a part value where the
    operator defines one (a skill below the required level), and None when unknown."""

    outcome: str
    score: float | None = None
    note: str = ""


@dataclass(frozen=True)
class Operator:
    code: str
    label: str
    expects: str  # what the factor's ``value`` must look like, shown in the rules screen
    fn: Callable[[object, object, date], Check]


OPERATORS: dict[str, Operator] = {}


class CannotCompare(Exception):
    """The value has the wrong shape for this operator. Reported as unknown with a note."""


def operator(code, label, expects):
    def wrap(fn):
        OPERATORS[code] = Operator(code, label, expects, fn)
        return fn

    return wrap


def _yes(ok: bool) -> Check:
    return Check(PASS, 1.0) if ok else Check(FAIL, 0.0)


def _norm(v):
    return v.strip().casefold() if isinstance(v, str) else v


def _date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            raise CannotCompare(f"'{v}' is not a date") from None
    raise CannotCompare("a date is needed")


def _number(v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise CannotCompare("a number is needed")
    return float(v)


def _ordered(v):
    """Numbers compare as numbers; anything else must be a date."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return _date(v)


def _pair(v, what):
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        raise CannotCompare(f"{what} must be a pair [from, to]")
    return v


def _same_kind(a, b):
    if type(a) is not type(b):
        raise CannotCompare("cannot compare a number with a date")


@operator("eq", "is", "one value")
def _eq(actual, expected, today):
    return _yes(_norm(actual) == _norm(expected))


@operator("in", "is one of", "a list of values")
def _in(actual, expected, today):
    if not isinstance(expected, (list, tuple)):
        raise CannotCompare("the rule needs a list of values")
    return _yes(_norm(actual) in [_norm(e) for e in expected])


@operator("gte", "is at least", "a number or a date")
def _gte(actual, expected, today):
    a, e = _ordered(actual), _ordered(expected)
    _same_kind(a, e)
    return _yes(a >= e)


@operator("lte", "is at most", "a number or a date")
def _lte(actual, expected, today):
    a, e = _ordered(actual), _ordered(expected)
    _same_kind(a, e)
    return _yes(a <= e)


@operator("between", "is between", "a pair [lowest, highest]")
def _between(actual, expected, today):
    lo, hi = (_ordered(x) for x in _pair(expected, "the rule's range"))
    a = _ordered(actual)
    _same_kind(a, lo)
    _same_kind(a, hi)
    return _yes(lo <= a <= hi)


@operator("within_km", "is within a distance of", "{lat, lon, km}")
def _within_km(actual, expected, today):
    try:
        lat1, lon1 = _number(actual["lat"]), _number(actual["lon"])
        lat2, lon2 = _number(expected["lat"]), _number(expected["lon"])
        limit = _number(expected["km"])
    except (KeyError, TypeError):
        raise CannotCompare("coordinates {lat, lon} and a distance in km are needed") from None
    # Haversine great-circle distance; 6371 km is the mean radius of the Earth.
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return _yes(2 * 6371 * asin(sqrt(h)) <= limit)


@operator("overlaps", "overlaps the dates", "a pair of dates [from, to]")
def _overlaps(actual, expected, today):
    a1, a2 = (_date(x) for x in _pair(actual, "the value"))
    e1, e2 = (_date(x) for x in _pair(expected, "the rule's dates"))
    return _yes(a1 <= e2 and e1 <= a2)


@operator("has_skill_level", "has the skill at level", "{skill, level}")
def _has_skill_level(actual, expected, today):
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        raise CannotCompare("a skill list and {skill, level} are needed")
    try:
        skill, need = expected["skill"], _number(expected["level"])
    except KeyError:
        raise CannotCompare("the rule needs {skill, level}") from None
    have = actual.get(skill)
    if have is None:  # the skill list is known and this skill is not on it
        return Check(FAIL, 0.0)
    have = _number(have)
    if have >= need:
        return Check(PASS, 1.0)
    return Check(FAIL, round(have / need, 4) if need > 0 else 0.0, "below the level asked for")


@operator("count_gte", "counts at least", "a whole number")
def _count_gte(actual, expected, today):
    n = len(actual) if isinstance(actual, (list, tuple)) else _number(actual)
    return _yes(n >= _number(expected))


@operator("days_since_gte", "was at least this many days ago", "a number of days")
def _days_since_gte(actual, expected, today):
    return _yes((today - _date(actual)).days >= _number(expected))


def compare(code: str, actual, expected, today: date) -> Check:
    """Run one operator. Missing input on either side is unknown."""
    op = OPERATORS[code]
    if actual is None or actual == "":
        return Check(UNKNOWN, None, "no value recorded")
    if expected is None:
        return Check(UNKNOWN, None, "the rule's value is not set")
    try:
        return op.fn(actual, expected, today)
    except CannotCompare as exc:
        return Check(UNKNOWN, None, str(exc))
