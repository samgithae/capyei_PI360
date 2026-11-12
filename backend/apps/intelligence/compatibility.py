"""Module B: how well a youth fits an opportunity (doc 07 §4.3).

The rule version names the checks and their weights; the opportunity says which of them apply and
whether each is mandatory. An opportunity can carry several requirements of one kind (three
skills, say), so each requirement is checked on its own and shares its check's weight.

Mandatory checks give the group: not eligible if one fails, eligible with unknowns if none fails
but one is unknown, else eligible. Preferred checks give a score. A missing fact is unknown and
never a failure; a check set to "exclude" when its fact is missing is left out altogether."""

import pi360_rules
from pi360_rules.engine import check_factor

ELIGIBLE, UNKNOWNS, NOT_ELIGIBLE = "eligible", "eligible_with_unknowns", "not_eligible"
GROUP_ORDER = {ELIGIBLE: 0, UNKNOWNS: 1, NOT_ELIGIBLE: 2}
# The requirement category each factor type reads. Interests come from the opportunity's sector.
FOR_FACTOR = {"qualification": "qualification", "skill": "skill", "experience": "experience"}
NEEDS_VALUE = "This requirement has no structured value yet, so it was not checked."


def _jobs(definition, opp):
    """``[(factor, requirement-or-None, local snapshot values, label)]`` for this opportunity."""
    factors = {f.get("type"): f for f in definition.get("factors", []) if f.get("enabled", True)}
    jobs, skipped = [], []
    for r in opp["requirements"]:
        label = r["description"]
        if r["factor"] not in {"skill", "qualification", "experience", "availability"}:
            skipped.append({"label": label, "reason": "Not checked by the rules (free text)."})
        elif not r["structured"]:
            skipped.append({"label": label, "reason": NEEDS_VALUE})
        elif r["factor"] == "qualification" and "qualification" in factors:
            jobs.append(
                (
                    factors["qualification"],
                    r,
                    {"opportunity.required_education_level": r["level_rank"]},
                    label,
                )
            )
        elif r["factor"] == "skill" and "skill" in factors:
            need = {"skill": r["skill_id"], "level": 1}
            jobs.append((factors["skill"], r, {"opportunity.required_skill": need}, label))
        elif r["factor"] == "experience" and "experience" in factors:
            jobs.append(
                (
                    factors["experience"],
                    r,
                    {"opportunity.required_experience_months": r["min_months"]},
                    label,
                )
            )
        elif r["factor"] == "availability":
            if r["needed_by"] and "availability" in factors:
                jobs.append(
                    (factors["availability"], r, {"opportunity.start_date": r["needed_by"]}, label)
                )
            if r["work_pattern"] and "work_conditions" in factors:
                jobs.append(
                    (
                        factors["work_conditions"],
                        r,
                        {"opportunity.work_pattern": r["work_pattern"]},
                        label,
                    )
                )
    if opp["sector_id"] and "interests" in factors:
        jobs.append(
            (
                factors["interests"],
                None,
                {"opportunity.sector": opp["sector_id"]},
                "Opportunity sector is one the youth is interested in",
            )
        )
    return jobs, skipped


def _weights(definition, jobs):
    """Each job's share of its factor's weight (None while the weight is undecided)."""
    per_factor: dict = {}
    for factor, *_ in jobs:
        per_factor[factor["code"]] = per_factor.get(factor["code"], 0) + 1
    out = []
    for factor, *_ in jobs:
        weight = pi360_rules.engine._weight(factor, definition)
        out.append(None if weight is None else weight / per_factor[factor["code"]])
    return out


def _apply_grade(check, req, snapshot):
    """Tighten a passed qualification check when the requirement names a minimum grade.

    A higher level than required passes outright. At the required level the youth's best grade
    must reach the minimum: lower fails, none recorded is unknown. The rule definition itself
    only compares levels, so this is done here and the check keeps its weight and source."""
    need = req["min_grade_rank"] if req else None
    if need is None or check["outcome"] != pi360_rules.PASS:
        return
    fact = snapshot.get("participant.education_grade")
    if not fact:
        return
    have = fact["value"]
    if have["level_rank"] > req["level_rank"]:
        return
    check["source"] = fact.get("source", check.get("source"))
    check["verified"] = fact.get("verified", check.get("verified"))
    if have["grade_rank"] is None:
        check.update(outcome=pi360_rules.UNKNOWN, score=None, note="Grade not recorded.")
    elif have["grade_rank"] < need:
        check.update(
            outcome=pi360_rules.FAIL,
            score=0,
            note=f"Grade {have['grade']} is below the minimum {req['min_grade']}.",
        )
    else:
        check["note"] = f"Grade {have['grade']} meets the minimum {req['min_grade']}."


def assess(definition: dict, opp: dict, snapshot: dict, today) -> dict:
    """The group, score and every check for one youth. ``snapshot`` is the youth's facts."""
    jobs, skipped = _jobs(definition, opp)
    weights = _weights(definition, jobs)
    checks = []
    for (factor, req, local, label), weight in zip(jobs, weights, strict=True):
        mandatory = bool(req and req["mandatory"])
        c = check_factor(
            dict(factor, mandatory=mandatory), definition, {**snapshot, **local}, today
        )
        if factor.get("type") == "qualification":
            _apply_grade(c, req, snapshot)
        c["label"], c["weight"] = label, weight
        if c["outcome"] == pi360_rules.UNKNOWN and c["unknown_policy"] == "exclude":
            c["outcome"] = "excluded"
        checks.append(c)
    live = [c for c in checks if c["outcome"] != "excluded"]
    mandatory = [c for c in live if c["mandatory"]]
    if any(c["outcome"] == pi360_rules.FAIL for c in mandatory):
        group = NOT_ELIGIBLE
    elif any(c["outcome"] == pi360_rules.UNKNOWN for c in mandatory):
        group = UNKNOWNS
    else:
        group = ELIGIBLE
    preferred = [c for c in live if not c["mandatory"]]
    known = [c for c in preferred if c["outcome"] != pi360_rules.UNKNOWN]
    score = coverage = None
    if preferred and all(c["weight"] is not None for c in preferred):
        total = sum(c["weight"] for c in preferred)
        have = sum(c["weight"] for c in known)
        coverage = round(have / total, 4) if total else None
        if have:
            score = round(sum(c["weight"] * (c["score"] or 0) for c in known) / have * 100)
    met = sum(1 for c in live if c["outcome"] == pi360_rules.PASS)
    return {
        "group": group,
        "met": met,
        "checked": len(live),
        # Preferred checks exist but a weight is still undecided (D-009), so no % can be given.
        "weights_pending": bool(preferred) and any(c["weight"] is None for c in preferred),
        "score": score,
        "coverage": coverage,
        "checks": [
            {k: c[k] for k in ("label", "mandatory", "outcome", "note", "source", "verified")}
            for c in checks
        ],
        "missing": [c["label"] for c in live if c["outcome"] == pi360_rules.UNKNOWN],
        "not_checked": skipped,
    }
