"""Data-quality rules for the youth records (T-074, DATA-14, INT-06).

Each rule is a plain, checkable statement about one record, with what to do about it. They look
only at what PI360 holds, so a record that fails is either wrong in the MIS or incomplete there;
the fix is made on the youth's profile and, for MIS-owned values, travels back through the
correction export (see ``corrections``). Age limits are working defaults until CAP-YEI decides
the age range."""

from dataclasses import dataclass

from django.db.models import Exists, F, OuterRef, Q
from django.utils import timezone

from .models import Participant, ParticipantContact, ParticipantEnrollment

AGE_MIN, AGE_MAX = 14, 35


@dataclass(frozen=True)
class Rule:
    code: str
    label: str
    fix: str


def _years_ago(today, n):
    try:
        return today.replace(year=today.year - n)
    except ValueError:  # 29 February
        return today.replace(year=today.year - n, day=28)


def _enrolment(**kw):
    return Exists(ParticipantEnrollment.objects.filter(participant=OuterRef("pk"), **kw))


def _conditions(today) -> dict:
    young = _years_ago(today, AGE_MIN)
    old = _years_ago(today, AGE_MAX + 1)
    return {
        "no_county": Q(origin_county__isnull=True),
        "gender_unknown": Q(gender=Participant.GENDER_UNKNOWN),
        "age_missing": Q(age_at_source__isnull=True, date_of_birth__isnull=True),
        "age_range": (
            Q(date_of_birth__isnull=True)
            & (Q(age_at_source__lt=AGE_MIN) | Q(age_at_source__gt=AGE_MAX))
        )
        | Q(date_of_birth__gt=young)
        | Q(date_of_birth__lte=old),
        "status_unknown": _enrolment(status=ParticipantEnrollment.UNKNOWN),
        "no_contact": ~Exists(ParticipantContact.objects.filter(participant=OuterRef("pk"))),
        "no_mis_number": _enrolment(source_enrollment_no=""),
        "dates_reversed": _enrolment(completed_on__lt=F("enrolled_on")),
        "single_name": Q(full_name_source__regex=r"^\s*\S+\s*$"),
    }


RULES = [
    Rule("no_county", "No county", "Add the county the youth comes from."),
    Rule("gender_unknown", "Gender not recorded", "Record the gender the youth gives."),
    Rule("age_missing", "No age or date of birth", "Record the age or the date of birth."),
    Rule(
        "age_range",
        f"Age outside {AGE_MIN} to {AGE_MAX}",
        "Check the age or date of birth against the source sheet.",
    ),
    Rule("status_unknown", "Enrolment status not known", "Set whether they are enrolled."),
    Rule("no_contact", "No phone or email", "Add a way to reach the youth."),
    Rule(
        "no_mis_number",
        "No MIS enrolment number",
        "Add the number so fixes can be matched to the MIS.",
    ),
    Rule(
        "dates_reversed",
        "Completed before enrolled",
        "Correct the enrolment or completion date.",
    ),
    Rule("single_name", "Only one name", "Add the family name if the youth has one."),
]
BY_CODE = {r.code: r for r in RULES}


class UnknownRule(ValueError):
    pass


def _base(user):
    return Participant.objects.visible_to(user)


def summary(user) -> dict:
    """How many visible youth fail each rule, and how many fail at least one."""
    conds = _conditions(timezone.localdate())
    base = _base(user)
    any_q = Q()
    rules = []
    for r in RULES:
        c = conds[r.code]
        any_q |= Q(c)
        count = base.filter(c).count()
        rules.append({"code": r.code, "label": r.label, "fix": r.fix, "count": count})
    return {"checked": base.count(), "failing": base.filter(any_q).count(), "rules": rules}


def records(user, *, rule=None, q="", offset=0, size=25) -> dict:
    """A page of youth failing ``rule`` (or any rule), each with every rule it fails."""
    conds = _conditions(timezone.localdate())
    qs = _base(user)
    if rule:
        if rule not in conds:
            raise UnknownRule("Unknown rule.")
        qs = qs.filter(conds[rule])
    else:
        any_q = Q()
        for c in conds.values():
            any_q |= Q(c)
        qs = qs.filter(any_q)
    if q.strip():
        qs = qs.filter(full_name_source__icontains=q.strip())
    total = qs.count()
    page = list(
        qs.select_related("origin_county")
        .prefetch_related("enrollments__project")
        .order_by("full_name_source", "pk")[offset : offset + size]
    )
    ids = [p.pk for p in page]
    failing = {p.pk: [] for p in page}
    for r in RULES:
        for pk in _base(user).filter(pk__in=ids).filter(conds[r.code]).values_list("pk", flat=True):
            failing[pk].append(r.code)
    return {
        "total": total,
        "page_size": size,
        "results": [
            {
                "id": str(p.pk),
                "name": p.full_name_source,
                "county": p.origin_county.name if p.origin_county_id else "",
                "projects": sorted({e.project.name for e in p.enrollments.all()}),
                "enrollment_numbers": sorted(
                    e.source_enrollment_no for e in p.enrollments.all() if e.source_enrollment_no
                ),
                "issues": [
                    {"code": c, "label": BY_CODE[c].label, "fix": BY_CODE[c].fix}
                    for c in failing[p.pk]
                ],
            }
            for p in page
        ],
    }
