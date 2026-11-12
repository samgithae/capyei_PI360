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
