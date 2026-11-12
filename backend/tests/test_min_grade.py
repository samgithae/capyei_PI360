"""Minimum grade on a requirement ("secondary, C or above") and how matching reads it."""

import pytest

from apps.configuration.models import QualificationGrade, QualificationLevel
from apps.employers.models import Employer, Opportunity, OpportunityRequirement
from apps.participants.models import Participant, ParticipantQualification
from tests.test_suggestions import activate_compatibility, api

BLANK = {
    "qualification_level_id": None, "min_grade_id": None, "skill_id": None,
    "min_months": None, "needed_by": None, "work_pattern": "",
}  # fmt: skip


def grade(level_code, name):
    return QualificationGrade.objects.get(level__code=level_code, name=name)


@pytest.fixture
def opp(db):
    return Opportunity.objects.create(
        employer=Employer.objects.create(name="Acme"), title="Clerk", status="open"
    )


def add(client, opp, **body):
    return client.post(
        f"/api/v1/opportunities/{opp.pk}/requirements",
        {**BLANK, "factor": "qualification", "is_mandatory": True, **body},
        content_type="application/json",
    )


def test_requirement_stores_grade_and_describes_it(opp, make_user):
    admin = api(make_user("admin", "Administrator"))
    sec = QualificationLevel.objects.get(code="QL02")
    r = add(admin, opp, qualification_level_id=str(sec.pk), min_grade_id=str(grade("QL02", "C").pk))
    assert r.status_code == 201, r.content
    row = OpportunityRequirement.objects.get(opportunity=opp)
    assert row.min_grade.name == "C" and row.description.endswith("grade C or above")
    assert r.json()["min_grade_id"] == str(row.min_grade_id)


def test_grade_must_belong_to_the_chosen_level(opp, make_user):
    admin = api(make_user("admin", "Administrator"))
    dip = QualificationLevel.objects.get(code="QL05")
    r = add(admin, opp, qualification_level_id=str(dip.pk), min_grade_id=str(grade("QL02", "C").pk))
    assert r.status_code == 409
    r = add(admin, opp, min_grade_id=str(grade("QL02", "C").pk))  # no level at all
    assert r.status_code == 409


def test_changing_the_level_drops_a_grade_that_no_longer_fits(opp, make_user):
    admin = api(make_user("admin", "Administrator"))
    sec = QualificationLevel.objects.get(code="QL02")
    made = add(
        admin, opp, qualification_level_id=str(sec.pk), min_grade_id=str(grade("QL02", "C").pk)
    ).json()
    dip = QualificationLevel.objects.get(code="QL05")
    r = admin.patch(
        f"/api/v1/opportunities/{opp.pk}/requirements/{made['id']}",
        {"qualification_level_id": str(dip.pk), "description": ""},
        content_type="application/json",
    )
    assert r.status_code == 200, r.content
    assert OpportunityRequirement.objects.get(pk=made["id"]).min_grade_id is None


def youth(name, level_code, grade_name=None):
    p = Participant.objects.create(full_name_source=name)
    ParticipantQualification.objects.create(
        participant=p,
        level=QualificationLevel.objects.get(code=level_code),
        grade=grade("QL02", grade_name) if grade_name else None,
    )
    return p


def test_matching_checks_the_minimum_grade(opp, make_user):
    activate_compatibility()
    admin = api(make_user("admin", "Administrator"))
    sec = QualificationLevel.objects.get(code="QL02")
    add(admin, opp, qualification_level_id=str(sec.pk), min_grade_id=str(grade("QL02", "C").pk))
    youth("Meets", "QL02", "B")
    youth("Exactly", "QL02", "C")
    youth("Below", "QL02", "D+")
    youth("Unrecorded", "QL02")
    youth("Higher level", "QL05")  # a diploma outranks secondary, whatever the grade
    body = admin.get(f"/api/v1/opportunities/{opp.pk}/suggestions").json()
    by = {s["name"]: s for s in body["suggestions"]}
    assert by["Meets"]["group"] == "eligible"
    assert by["Exactly"]["group"] == "eligible"
    assert by["Below"]["group"] == "not_eligible"
    assert by["Unrecorded"]["group"] == "eligible_with_unknowns"
    assert by["Higher level"]["group"] == "eligible"
    assert any("below the minimum" in (c["note"] or "") for c in by["Below"]["checks"])
    assert by["Unrecorded"]["missing"]


def test_a_requirement_without_a_grade_ignores_grades(opp, make_user):
    activate_compatibility()
    admin = api(make_user("admin", "Administrator"))
    sec = QualificationLevel.objects.get(code="QL02")
    add(admin, opp, qualification_level_id=str(sec.pk))
    youth("Low grade", "QL02", "E")
    by = {
        s["name"]: s
        for s in admin.get(f"/api/v1/opportunities/{opp.pk}/suggestions").json()["suggestions"]
    }
    assert by["Low grade"]["group"] == "eligible"
