"""The numbers behind the support-priority flags (Module A) and the employer evidence (Module C).

CAP-YEI has not fixed these yet (D-008, D-013, D-028), so each has a starting value here that an
administrator can change on the Rules settings page. Adding a number later is one entry below;
nothing else needs to change."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Setting:
    key: str
    group: str  # "A", "C", "E" or "R"
    label: str
    unit: str
    default: int
    minimum: int
    help: str


REGISTRY = [
    Setting(
        "support.unsuccessful", "A", "Unsuccessful referrals before a flag", "referrals", 2, 1,
        "A youth with this many unsuccessful referrals in the window below is flagged.",
    ),
    Setting(
        "support.window_days", "A", "Window for counting unsuccessful referrals", "days", 90, 7,
        "How far back unsuccessful referrals are counted.",
    ),
    Setting(
        "support.stalled_days", "A", "Days with no movement before a flag", "days", 60, 7,
        "A youth whose open referral has not changed stage for this long is flagged.",
    ),
    Setting(
        "support.unreferred_days", "A", "Days available but never referred", "days", 30, 7,
        "An enrolled youth who is ready for work but has no referral after this long is flagged.",
    ),
    Setting(
        "support.review_days", "A", "Days a reviewed flag stays quiet", "days", 14, 1,
        "After an officer reviews a flagged youth, the flag is hidden from the queue this long.",
    ),
    Setting(
        "employer.min_referrals", "C", "Referrals needed before a result", "referrals", 5, 1,
        "Below this many referrals in the window an employer shows 'insufficient evidence'.",
    ),
    Setting(
        "employer.min_retention_checks", "C", "Check-ins needed before retention shows",
        "check-ins", 5, 1,
        "Below this many completed retention check-ins, retention shows counts but no percentage.",
    ),
    Setting(
        "employer.min_feedback", "C", "Feedback entries needed before a result", "entries", 5, 1,
        "Below this many logged feedback entries in the period, feedback shows counts but no "
        "percentage.",
    ),
    Setting(
        "employer.positive_rating", "C", "Lowest rating that counts as positive", "out of 5", 4, 1,
        "Feedback rated this or higher (out of 5) is counted as positive.",
    ),
    Setting(
        "employer.window_days", "C", "Period the evidence covers", "days", 180, 30,
        "Referrals sent in this many days are counted.",
    ),
    Setting(
        "rules.review_days", "R", "Days between reviews of a rule", "days", 90, 7,
        "A rule in force longer than this is marked 'Review due' on the Rules page. Working value "
        "until the sponsor sets the cadence (D-009).",
    ),
    Setting(
        "exports.small_cell", "E", "Smallest group an export may show", "youth", 5, 2,
        "Counts below this are hidden and youth in smaller groups are left out. Awaiting D-045.",
    ),
    Setting(
        "exports.expiry_days", "E", "Days an export file is kept", "days", 7, 1,
        "After this the file is deleted. The log of who exported what is kept.",
    ),
]  # fmt: skip
BY_KEY = {s.key: s for s in REGISTRY}
