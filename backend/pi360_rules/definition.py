"""Shape of a rule version's definition, and the checks a definition must pass before it can
be sent for review (doc 07 §2.1).

    {
      "factors": [
        {"code": "A-TIME", "label": "Time without transition", "type": "time",
         "operator": "days_since_gte", "field": "participant.training_completed_on",
         "value": {"param": "theta_time"}, "mandatory": false, "weight": 1,
         "unknown_policy": "flag", "max_age_days": 365}
      ],
      "parameters": {
        "theta_time": {"label": "Days without a transition", "value": null,
                       "approved": false, "decision": "D-026", "unit": "days"}
      }
    }

A factor's ``value`` is a literal, ``{"param": name}`` (a threshold from ``parameters``) or
``{"field": name}`` (another field of the snapshot, such as an opportunity requirement)."""

from .operators import OPERATORS

MODULES = ("A", "B", "C")
UNKNOWN_POLICIES = ("flag", "exclude")
FACTOR_KEYS = {
    "code", "label", "type", "operator", "field", "value", "mandatory",
    "mandatory_from_requirement", "weight", "unknown_policy", "max_age_days", "enabled", "note",
}  # fmt: skip
PARAMETER_KEYS = {"label", "value", "approved", "decision", "unit", "note"}


def _problem(path, message):
    return {"path": path, "message": message}


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _ref(value, kind):
    """The name inside {"param": name} or {"field": name}, else None."""
    if isinstance(value, dict) and set(value) == {kind} and isinstance(value[kind], str):
        return value[kind]
    return None


def validate(definition) -> list[dict]:
    """Every problem in a definition as ``{"path", "message"}``. An empty list means it is
    well formed. It does not check that parameters are approved; see ``unapproved``."""
    if not isinstance(definition, dict):
        return [_problem("", "The definition must be a JSON object.")]
    problems = []
    for key in sorted(set(definition) - {"factors", "parameters", "notes"}):
        problems.append(_problem(key, "Unknown key. Use factors, parameters and notes."))

    parameters = definition.get("parameters", {})
    if not isinstance(parameters, dict):
        problems.append(_problem("parameters", "Must be an object of name: {value, approved}."))
        parameters = {}
    for name, p in parameters.items():
        path = f"parameters.{name}"
        if not isinstance(p, dict):
            problems.append(_problem(path, "Must be an object with value and approved."))
            continue
        for key in sorted(set(p) - PARAMETER_KEYS):
            problems.append(_problem(f"{path}.{key}", "Unknown key."))
        if "value" not in p:
            problems.append(_problem(path, "Needs a value (use null while it is undecided)."))
        if not isinstance(p.get("approved", False), bool):
            problems.append(_problem(f"{path}.approved", "Must be true or false."))
        if p.get("approved") is True and p.get("value") is None:
            problems.append(_problem(path, "An approved parameter needs a value."))

    factors = definition.get("factors")
    if not isinstance(factors, list) or not factors:
        problems.append(_problem("factors", "Add at least one factor."))
        return problems
    seen = set()
    for i, f in enumerate(factors):
        path = f"factors[{i}]"
        if not isinstance(f, dict):
            problems.append(_problem(path, "Must be an object."))
            continue
        for key in sorted(set(f) - FACTOR_KEYS):
            problems.append(_problem(f"{path}.{key}", "Unknown key."))
        code = f.get("code")
        if not isinstance(code, str) or not code.strip():
            problems.append(_problem(f"{path}.code", "Needs a code."))
        elif code in seen:
            problems.append(_problem(f"{path}.code", f"Code {code} is used twice."))
        else:
            seen.add(code)
        if not isinstance(f.get("label"), str) or not f.get("label", "").strip():
            problems.append(_problem(f"{path}.label", "Needs a plain-language label."))
        if f.get("operator") not in OPERATORS:
            known = ", ".join(sorted(OPERATORS))
            problems.append(_problem(f"{path}.operator", f"Unknown operator. Use one of: {known}."))
        if not isinstance(f.get("field"), str) or not f.get("field", "").strip():
            problems.append(_problem(f"{path}.field", "Needs the snapshot field it reads."))
        if "value" not in f:
            problems.append(_problem(f"{path}.value", "Needs a value, a parameter or a field."))
        elif (name := _ref(f["value"], "param")) is not None and name not in parameters:
            problems.append(_problem(f"{path}.value", f"Parameter {name} is not defined."))
        weight = f.get("weight", 1)
        if not _is_number(weight) or weight < 0:
            problems.append(_problem(f"{path}.weight", "Must be a number, zero or more."))
        for flag in ("mandatory", "mandatory_from_requirement", "enabled"):
            if not isinstance(f.get(flag, False), bool):
                problems.append(_problem(f"{path}.{flag}", "Must be true or false."))
        if f.get("unknown_policy", "flag") not in UNKNOWN_POLICIES:
            problems.append(_problem(f"{path}.unknown_policy", "Use flag or exclude."))
        age = f.get("max_age_days")
        if age is not None and (not _is_number(age) or age <= 0):
            problems.append(_problem(f"{path}.max_age_days", "Must be a number above zero."))
    return problems


def unapproved(definition) -> list[str]:
    """Names of parameters that still wait for a decision: not marked approved, or no value.
    A version cannot be approved while this list is not empty (T-048)."""
    if not isinstance(definition, dict) or not isinstance(definition.get("parameters"), dict):
        return []
    return sorted(
        name
        for name, p in definition["parameters"].items()
        if not isinstance(p, dict) or p.get("approved") is not True or p.get("value") is None
    )
