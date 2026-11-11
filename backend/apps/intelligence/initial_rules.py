"""Draft rule versions for the product owner to review (T-048, doc 07 §3 to §5).

These give each module its structure: which factors exist, which operator each one uses and
which snapshot field it reads. They hold **no threshold, weight or minimum count**. Every
number is a parameter with ``value: null`` and ``approved: false``, tagged with the decision
that will set it (doc 12), so nothing can be approved or activated until CAP-YEI decides.

Field names such as ``participant.last_transition_on`` are the names the snapshot builders
will use (T-060, T-063, T-067). They are proposals too."""

from . import services
from .models import RuleSet


def _undecided(label, decision, unit="", note=""):
    p = {"label": label, "value": None, "approved": False, "decision": decision}
    if unit:
        p["unit"] = unit
    if note:
        p["note"] = note
    return p


def _factor(code, label, kind, operator, field, value, note="", **more):
    f = {
        "code": code,
        "label": label,
        "type": kind,
        "operator": operator,
        "field": field,
        "value": value,
        "unknown_policy": "flag",
        **more,
    }
    if note:
        f["note"] = note
    return f


def _param(name):
    return {"param": name}


def _field(name):
    return {"field": name}


# ---- Module A: placement support priority (doc 07 §3.1) ---------------------------------------

SUPPORT_PRIORITY = {
    "factors": [
        _factor(
            "A-GAPS", "Outstanding readiness gaps", "readiness", "count_gte",
            "participant.open_readiness_gaps", _param("theta_gaps"),
            "Open readiness items, such as a missing required document or skill. "
            "Which items count is part of D-026.",
        ),
        _factor(
            "A-REFERRALS", "Repeated unsuccessful referrals", "referral", "count_gte",
            "participant.unsuccessful_referrals_in_window", _param("theta_unsuccessful"),
            "Referrals closed as rejected or no response in the last theta_window days. "
            "Which close reasons count is part of D-026; the stage list is D-037.",
        ),
        _factor(
            "A-DOCS", "Unresolved documentation barrier", "documentation", "days_since_gte",
            "participant.oldest_open_document_barrier_on", _param("theta_doc"),
            "The oldest documentation barrier that is still open. Barrier types are part "
            "of D-026.",
        ),
        _factor(
            "A-TIME", "Time without transition", "time", "days_since_gte",
            "participant.last_transition_on", _param("theta_time"),
            "Days since training ended, or since the last employment episode ended, with no "
            "episode open. The start event is part of D-026.",
        ),
    ],
    "parameters": {
        "theta_gaps": _undecided("Open readiness gaps that raise a flag", "D-026", "items"),
        "theta_unsuccessful": _undecided(
            "Unsuccessful referrals that raise a flag", "D-026", "referrals"
        ),
        "theta_window": _undecided(
            "Period in which unsuccessful referrals are counted", "D-026", "days",
            "Used when the referrals are counted, before the check runs.",
        ),
        "theta_doc": _undecided(
            "Days a documentation barrier may stay open", "D-026", "days"
        ),
        "theta_time": _undecided("Days without a transition", "D-026", "days"),
    },
    "notes": (
        "A check that passes means the indicator applies and the participant is put in the "
        "staff review queue. A flag never limits which opportunities a participant can be "
        "matched or referred to. No priority bands and no risk score unless D-026 asks for "
        "them. A YDM factor is not included; it can be added only after D-001 and D-026."
    ),
}  # fmt: skip


# ---- Module B: opportunity compatibility (doc 07 §4.3) ----------------------------------------

_FROM_OPPORTUNITY = "Mandatory or preferred as each opportunity says (D-008)."
_CLASSIFY = "Whether this is mandatory or preferred is D-008."

COMPATIBILITY = {
    "factors": [
        _factor(
            "B-QUAL", "Qualification", "qualification", "gte",
            "participant.education_level", _field("opportunity.required_education_level"),
            _FROM_OPPORTUNITY + " Verified and self-reported values are shown apart.",
            mandatory_from_requirement=True, weight=_param("w_qualification"),
        ),
        _factor(
            "B-SKILL", "Skill or competency", "skill", "has_skill_level",
            "participant.skills", _field("opportunity.required_skill"),
            _FROM_OPPORTUNITY + " A skill below the level asked for counts in part. "
            "The skills list is D-038.",
            mandatory_from_requirement=True, weight=_param("w_skill"),
        ),
        _factor(
            "B-EXP", "Experience", "experience", "gte",
            "participant.experience_months", _field("opportunity.required_experience_months"),
            _FROM_OPPORTUNITY,
            mandatory_from_requirement=True, weight=_param("w_experience"),
        ),
        _factor(
            "B-LOC", "Location", "location", "within_km",
            "participant.location", _field("opportunity.location_within"),
            _FROM_OPPORTUNITY + " Uses theta_distance_km. Needs location codes with "
            "coordinates (D-038). Willingness to relocate is not yet captured.",
            mandatory_from_requirement=True, weight=_param("w_location"),
        ),
        _factor(
            "B-AVAIL", "Availability", "availability", "lte",
            "participant.available_from", _field("opportunity.start_date"),
            _FROM_OPPORTUNITY + " The participant is available on or before the start date.",
            mandatory_from_requirement=True, weight=_param("w_availability"),
        ),
        _factor(
            "B-INT", "Interests", "interests", "in",
            "opportunity.sector", _field("participant.interest_sectors"),
            "The opportunity's sector is one the participant chose. " + _CLASSIFY,
            weight=_param("w_interests"),
        ),
        _factor(
            "B-COND", "Work conditions", "work_conditions", "in",
            "opportunity.work_pattern", _field("participant.acceptable_work_patterns"),
            "Only if work conditions are captured on the profile. " + _CLASSIFY,
            weight=_param("w_conditions"),
        ),
    ],
    "parameters": {
        "w_qualification": _undecided("Weight: qualification", "D-009", "weight"),
        "w_skill": _undecided("Weight: skill or competency", "D-009", "weight"),
        "w_experience": _undecided("Weight: experience", "D-009", "weight"),
        "w_location": _undecided("Weight: location", "D-009", "weight"),
        "w_availability": _undecided("Weight: availability", "D-009", "weight"),
        "w_interests": _undecided("Weight: interests", "D-009", "weight"),
        "w_conditions": _undecided("Weight: work conditions", "D-009", "weight"),
        "theta_distance_km": _undecided(
            "Distance that counts as near the workplace", "D-008", "km",
            "Used when the opportunity's location is prepared, before the check runs.",
        ),
    },
    "notes": (
        "Mandatory checks give the group: eligible, eligible with unknowns, or not eligible. "
        "A missing value is unknown, never a fail. Preferred factors give a score and a "
        "coverage figure; CAP-YEI may prefer a simple count of factors met (D-009). The "
        "officer accepts or overrides every suggestion with a reason. A YDM factor is not "
        "included; it can be added only after D-001 and D-008."
    ),
}  # fmt: skip


# ---- Module C: employer reliability (doc 07 §5.1) ---------------------------------------------

_ENOUGH = "Shown only when this count reaches theta_min; otherwise 'insufficient evidence'."

EMPLOYER_RELIABILITY = {
    "factors": [
        _factor(
            "C-RESPONSE", "Response rate", "indicator", "count_gte",
            "employer.referrals_sent_in_window", _param("theta_min"),
            "Referrals with an employer response divided by referrals sent in the window. "
            + _ENOUGH + " 'No response' follows D-037.",
        ),
        _factor(
            "C-RESPONSE-TIME", "Median time to response", "indicator", "count_gte",
            "employer.referrals_answered_in_window", _param("theta_min"),
            "Median days from referral to the first response. " + _ENOUGH,
        ),
        _factor(
            "C-INTERVIEW", "Interview conversion", "indicator", "count_gte",
            "employer.referrals_sent_in_window", _param("theta_min"),
            "Referrals that reached interview divided by referrals sent. " + _ENOUGH,
        ),
        _factor(
            "C-PLACEMENT", "Placement conversion", "indicator", "count_gte",
            "employer.referrals_sent_in_window", _param("theta_min"),
            "Referrals placed divided by referrals sent. " + _ENOUGH,
        ),
        _factor(
            "C-RETENTION", "Early retention", "indicator", "count_gte",
            "employer.placements_due_for_early_follow_up", _param("theta_min"),
            "Placements still active at the early follow-up point divided by placements due "
            "for that check. Only verified follow-ups count. " + _ENOUGH,
        ),
        _factor(
            "C-FEEDBACK", "Feedback", "indicator", "count_gte",
            "employer.feedback_in_window", _param("theta_min"),
            "Summary of participant and employer feedback. The verification rule is part of "
            "D-013. " + _ENOUGH,
        ),
    ],
    "parameters": {
        "theta_min": _undecided(
            "Fewest records needed to show an indicator", "D-013", "records"
        ),
        "theta_window": _undecided(
            "Period the indicators look back over", "D-013", "days",
            "Used when the records are counted, before the check runs.",
        ),
        "theta_follow_up": _undecided(
            "Early follow-up point after a placement starts", "D-028", "days",
            "Used when placements due for the early check are counted.",
        ),
    },
    "notes": (
        "Each factor checks that there is enough evidence to show its indicator. Every "
        "indicator shows the count, the period, the source and the date worked out. Terms "
        "and conditions (pay band, contract type, hours) are shown as recorded and are not "
        "scored. There is no overall score unless D-027 decides otherwise. The indicators "
        "reflect only referrals recorded in PI 360."
    ),
}  # fmt: skip


INITIAL = [
    {
        "module": "A",
        "code": "support-priority",
        "name": "Placement support priority",
        "purpose": "Finds participants who may need follow-up or extra support. A prompt "
        "for staff; it never limits access to opportunities.",
        "definition": SUPPORT_PRIORITY,
    },
    {
        "module": "B",
        "code": "compatibility-default",
        "name": "Opportunity compatibility",
        "purpose": "Compares a participant with an opportunity's requirements, mandatory "
        "first and then preferred, and explains each factor.",
        "definition": COMPATIBILITY,
    },
    {
        "module": "C",
        "code": "employer-reliability",
        "name": "Employer reliability profile",
        "purpose": "Shows how an employer has responded to referrals and placements, with "
        "the amount of evidence behind each figure.",
        "definition": EMPLOYER_RELIABILITY,
    },
]

CHANGE_NOTES = (
    "First draft for product owner review (T-048). Structure only: every threshold and "
    "weight waits for a decision."
)


def load(actor=None) -> list[str]:
    """Create each initial rule set with version 1 as a draft. A rule set that already
    exists is left alone, so this is safe to run again. Returns the codes it created."""
    created = []
    for spec in INITIAL:
        if RuleSet.objects.filter(code=spec["code"]).exists():
            continue
        services.create_rule_set(actor=actor, change_notes=CHANGE_NOTES, **spec)
        created.append(spec["code"])
    return created
