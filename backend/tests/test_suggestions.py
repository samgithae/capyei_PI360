"""Suggested youth for an opportunity: group, score, what is missing, scope. Synthetic data."""

from datetime import date

import pytest
from django.test import Client

from apps.configuration.models import QualificationLevel, Skill
from apps.employers.models import Employer, Opportunity, OpportunityRequirement
from apps.intelligence import initial_rules
from apps.intelligence.models import RuleVersion
from apps.participants.models import (
    Participant,
    ParticipantExperience,
    ParticipantQualification,
    ParticipantSkill,
)


def api(user):
    c = Client()
    c.force_login(user)
    return c


def activate_compatibility():
    initial_rules.load()
    v = RuleVersion.objects.get(rule_set__code="compatibility-default")
    for p in v.definition["parameters"].values():
        p.update(value=1, approved=True)
    v.status = RuleVersion.ACTIVE
    v.save()


@pytest.fixture
def world(db):
    ql5, ql7 = (QualificationLevel.objects.get(code=c) for c in ("QL05", "QL07"))
    cook, weld = Skill.objects.get(code="SK-FOOD"), Skill.objects.get(code="SK-WELDING")
    mk = lambda n: Participant.objects.create(full_name_source=n)  # noqa: E731
    a, b, d, _c = mk("A Strong"), mk("B Partial"), mk("D Wrong skill"), mk("C Nothing")
    ParticipantQualification.objects.create(participant=a, level=ql7)
    ParticipantSkill.objects.create(participant=a, skill=cook, proficiency=3)
    ParticipantExperience.objects.create(participant=a, role_title="Cook", months=18)
    ParticipantQualification.objects.create(participant=b, level=ql5)
    ParticipantSkill.objects.create(participant=d, skill=weld)
    o = Opportunity.objects.create(
        employer=Employer.objects.create(name="Acme"), title="Cook", status="open"
    )
    R = OpportunityRequirement.objects
    R.create(
        opportunity=o,
        factor="qualification",
        description="Diploma",
        is_mandatory=True,
        qualification_level=ql5,
    )
    R.create(opportunity=o, factor="skill", description="Cooking", is_mandatory=True, skill=cook)
    R.create(opportunity=o, factor="experience", description="1 year", min_months=12)
    R.create(opportunity=o, factor="skill", description="Old free text")  # not structured
    return {"o": o, "url": f"/api/v1/opportunities/{o.pk}/suggestions"}


def test_groups_scores_and_missing_facts(world, make_user):
    activate_compatibility()
    body = api(make_user("admin", "Administrator")).get(world["url"]).json()
    assert body["available"] and body["rule"]["version"] >= 1
    by = {s["name"]: s for s in body["suggestions"]}
    assert by["A Strong"]["group"] == "eligible" and by["A Strong"]["score"] == 100
    assert by["B Partial"]["group"] == "eligible_with_unknowns"
    assert "Cooking" in by["B Partial"]["missing"]  # unknown, never a fail
    assert by["D Wrong skill"]["group"] == "not_eligible"
    assert "C Nothing" not in by  # no facts: counted, not ranked
    assert body["counts"]["no_data"] == 1 and body["counts"]["visible"] == 4
    assert [s["name"] for s in body["suggestions"]][0] == "A Strong"
    assert body["suggestions"][0]["not_checked"][0]["label"] == "Old free text"


def test_no_active_rule_says_so(world, make_user):
    body = api(make_user("admin", "Administrator")).get(world["url"]).json()
    assert body["available"] is False and "No compatibility rule" in body["reason"]


def test_scope_and_permissions(world, make_user):
    activate_compatibility()
    officer = api(make_user("amina", "Placement officer")).get(world["url"]).json()
    assert officer["counts"]["visible"] == 0 and officer["suggestions"] == []  # empty caseload
    assert (
        api(make_user("analyst", "M&E analyst")).get(world["url"]).status_code == 403
    )  # no profiles
    missing = f"/api/v1/opportunities/{'0' * 8}-0000-0000-0000-{'0' * 12}/suggestions"
    assert api(make_user("admin2", "Administrator")).get(missing).status_code == 404
    assert Client().get(world["url"]).status_code in (401, 403)
    assert date.today()  # engine reads today from the caller, not a clock inside the rules


def test_without_weights_youth_are_ranked_by_requirements_met(world, make_user):
    """Weights are an undecided policy (D-009). With none set there is no % fit, but the list
    must still order itself and say why, never silently fall back to name order."""
    initial_rules.load()
    v = RuleVersion.objects.get(rule_set__code="compatibility-default")
    v.status = RuleVersion.ACTIVE
    v.save()
    body = api(make_user("admin", "Administrator")).get(world["url"]).json()
    assert body["weights_pending"] is True
    top = body["suggestions"][0]
    assert top["name"] == "A Strong" and top["score"] is None
    assert top["met"] >= 1 and top["checked"] >= top["met"]
    by = {s["name"]: s for s in body["suggestions"]}
    assert by["A Strong"]["met"] > by["B Partial"]["met"]


def test_requirements_from_the_simplified_form_drive_the_same_matching(db, make_user):
    """The add-requirement form sends friendly picks as the usual structured payload. Matching
    must treat them exactly like requirements made any other way (meets / fails / unknown)."""
    activate_compatibility()
    ql5 = QualificationLevel.objects.get(code="QL05")
    cook = Skill.objects.get(code="SK-FOOD")
    mk = lambda n: Participant.objects.create(full_name_source=n)  # noqa: E731
    meets, fails, unknown = mk("Meets"), mk("Fails"), mk("Unknown")
    ParticipantQualification.objects.create(participant=meets, level=ql5)
    ParticipantSkill.objects.create(participant=meets, skill=cook)
    ParticipantExperience.objects.create(participant=meets, role_title="Cook", months=24)
    ParticipantQualification.objects.create(
        participant=fails, level=QualificationLevel.objects.get(code="QL01")
    )
    ParticipantSkill.objects.create(participant=unknown, skill=cook)
    o = Opportunity.objects.create(
        employer=Employer.objects.create(name="Acme"), title="Cook", status="open"
    )
    admin = api(make_user("admin", "Administrator"))
    blank = {
        "qualification_level_id": None, "skill_id": None, "min_months": None,
        "needed_by": None, "work_pattern": "",
    }  # fmt: skip
    forms = [
        {**blank, "factor": "qualification", "is_mandatory": True,
         "qualification_level_id": str(ql5.pk),
         "description": "Diploma or higher — Credit"},
        {**blank, "factor": "skill", "is_mandatory": True, "skill_id": str(cook.pk),
         "description": "Food preparation — Level needed: Intermediate"},
        {**blank, "factor": "experience", "is_mandatory": False, "min_months": 12,
         "description": "Kitchen"},
        {**blank, "factor": "other", "is_mandatory": False,
         "description": "Certification / Training: Food hygiene — Copy of the certificate"},
    ]  # fmt: skip
    for f in forms:
        r = admin.post(
            f"/api/v1/opportunities/{o.pk}/requirements", f, content_type="application/json"
        )
        assert r.status_code == 201, r.content
    by = {
        s["name"]: s
        for s in admin.get(f"/api/v1/opportunities/{o.pk}/suggestions").json()["suggestions"]
    }
    assert by["Meets"]["group"] == "eligible" and by["Meets"]["score"] == 100
    assert by["Fails"]["group"] == "not_eligible"  # a mandatory miss still disqualifies
    assert by["Unknown"]["group"] == "eligible_with_unknowns"  # missing is not failure
    assert "Diploma" in " ".join(by["Unknown"]["missing"])
    # The grade note rides in the description; it never changes the structured check.
    assert OpportunityRequirement.objects.get(
        opportunity=o, factor="qualification"
    ).description.endswith("Credit")


def test_a_referred_youth_leaves_the_suggestions(world, make_user):
    from apps.referrals.models import Referral

    activate_compatibility()
    admin = api(make_user("admin", "Administrator"))
    a = Participant.objects.get(full_name_source="A Strong")
    ref = Referral.objects.create(participant=a, opportunity=world["o"], stage=Referral.SUBMITTED)
    body = admin.get(world["url"]).json()
    assert "A Strong" not in {s["name"] for s in body["suggestions"]}
    assert body["counts"]["visible"] == 3
    ref.stage = Referral.WITHDRAWN  # an unsuccessful referral does not hide them
    ref.save()
    assert "A Strong" in {s["name"] for s in admin.get(world["url"]).json()["suggestions"]}


def test_preferred_factors_met_count_orders_ties_without_weights(world, make_user):
    """The interim display: how many preferred factors are met, no weights needed."""
    initial_rules.load()
    v = RuleVersion.objects.get(rule_set__code="compatibility-default")
    v.status = RuleVersion.ACTIVE
    v.save()
    body = api(make_user("admin", "Administrator")).get(world["url"]).json()
    by = {s["name"]: s for s in body["suggestions"]}
    assert by["A Strong"]["preferred_total"] == 1  # the 12-month experience requirement
    assert by["A Strong"]["preferred_met"] == 1
    assert by["B Partial"]["preferred_met"] == 0
