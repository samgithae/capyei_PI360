"""``evaluate(definition, snapshot, today)`` is a pure function (doc 07 §2.2): the same
definition, snapshot and date always give the same result. It reads no clock and no database,
so a stored result can be reproduced later from its rule version and input snapshot (AI-B9).

The snapshot holds only the fields the rules read. A field is either a bare value or

    {"value": ..., "source": "import", "verified": true, "as_of": "2026-10-01"}

so each check can show where its value came from and how old it is.

Modules add their own reading of the checks (eligibility groups for Module B, flags for
Module A) by registering an evaluator with ``@evaluator("B")``."""

from collections.abc import Callable
from datetime import date

from .operators import FAIL, PASS, UNKNOWN, Check, compare
from .operators import _date as _as_date

EVALUATORS: dict[str, Callable[[dict, list, dict], dict]] = {}


def evaluator(module: str):
    """Register the function that turns a module's checks into its output."""

    def wrap(fn):
        EVALUATORS[module] = fn
        return fn

    return wrap


def _field(snapshot: dict, name: str) -> dict:
    raw = snapshot.get(name)
    if isinstance(raw, dict) and "value" in raw:
        return raw
    return {"value": raw}


def _expected(factor: dict, definition: dict, snapshot: dict):
    """Resolve the factor's value. Returns (value, note for an unknown)."""
    value = factor.get("value")
    if isinstance(value, dict) and set(value) == {"param"}:
        p = (definition.get("parameters") or {}).get(value["param"]) or {}
        return p.get("value"), f"parameter {value['param']} has no value yet"
    if isinstance(value, dict) and set(value) == {"field"}:
        return _field(snapshot, value["field"]).get("value"), f"{value['field']} is not recorded"
    return value, "the rule's value is not set"


def check_factor(factor: dict, definition: dict, snapshot: dict, today: date) -> dict:
    field = _field(snapshot, factor["field"])
    expected, missing_note = _expected(factor, definition, snapshot)
    result = compare(factor["operator"], field.get("value"), expected, today)
    if result.outcome == UNKNOWN and expected is None and field.get("value") not in (None, ""):
        result = Check(UNKNOWN, None, missing_note)
    # A value older than the rule allows is treated as unknown, not as a fail (doc 07 §2.3).
    max_age, as_of = factor.get("max_age_days"), field.get("as_of")
    if result.outcome != UNKNOWN and max_age and as_of:
        age = (today - _as_date(as_of)).days
        if age > max_age:
            result = Check(UNKNOWN, None, f"value is {age} days old (limit {max_age})")
    return {
        "code": factor["code"],
        "label": factor.get("label", factor["code"]),
        "type": factor.get("type", ""),
        "operator": factor["operator"],
        "mandatory": bool(factor.get("mandatory", False)),
        "weight": factor.get("weight", 1),
        "unknown_policy": factor.get("unknown_policy", "flag"),
        "outcome": result.outcome,
        "score": result.score,
        "note": result.note,
        "actual": field.get("value"),
        "expected": expected,
        "source": field.get("source", ""),
        "verified": field.get("verified"),
        "as_of": field.get("as_of"),
    }


def evaluate(definition: dict, snapshot: dict, today: date, module: str | None = None) -> dict:
    """Check every enabled factor against the snapshot. With ``module``, the module's
    registered evaluator adds its own output under ``result``."""
    checks = [
        check_factor(f, definition, snapshot, today)
        for f in definition.get("factors", [])
        if f.get("enabled", True)
    ]
    out = {
        "checks": checks,
        "summary": {o: sum(1 for c in checks if c["outcome"] == o) for o in (PASS, FAIL, UNKNOWN)},
    }
    if module is not None and module in EVALUATORS:
        out["result"] = EVALUATORS[module](definition, checks, snapshot)
    return out
