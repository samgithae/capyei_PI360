"""Why a youth was put forward: the Compatibility checks for one referral. Synthetic data."""

import pytest
from django.test import Client

from apps.configuration.models import QualificationLevel, Skill
from apps.employers.models import Employer, Opportunity, OpportunityRequirement
from apps.identity import services as identity
from apps.participants.models import Participant, ParticipantQualification, ParticipantSkill
from apps.referrals.models import Referral

from .test_suggestions import activate_compatibility


def api(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def referral(db, make_user):
    officer = make_user("wanjiru", "Placement officer")
    identity.set_scopes(actor=None, user=officer, scopes=[("officer", "self")])
    ql5 = QualificationLevel.objects.get(code="QL05")
    cook = Skill.objects.get(code="SK-FOOD")
    youth = Participant.objects.create(full_name_source="Fit Youth", assigned_officer=officer)
    ParticipantQualification.objects.create(participant=youth, level=ql5)
    ParticipantSkill.objects.create(participant=youth, skill=cook, proficiency=2)
    opp = Opportunity.objects.create(
        employer=Employer.objects.create(name="Acme"), title="Cook", status="open"
    )
    R = OpportunityRequirement.objects
    R.create(
        opportunity=opp, factor="qualification", description="Diploma",
        is_mandatory=True, qualification_level=ql5,
    )  # fmt: skip
    R.create(opportunity=opp, factor="skill", description="Cooking", is_mandatory=True, skill=cook)
    R.create(opportunity=opp, factor="skill", description="Free text only")
    ref = Referral.objects.create(participant=youth, opportunity=opp)
    return {"ref": ref, "officer": officer, "url": f"/api/v1/referrals/{ref.pk}/fit"}


def test_fit_lists_each_check_for_the_pair(referral):
    activate_compatibility()
    body = api(referral["officer"]).get(referral["url"]).json()
    assert body["available"] and body["origin"] == referral["ref"].origin
    assert body["group"] == "eligible"
    assert {c["label"] for c in body["checks"]} >= {"Diploma", "Cooking"}
    assert all(c["outcome"] in {"pass", "fail", "unknown"} for c in body["checks"])
    assert body["not_checked"][0]["label"] == "Free text only"


def test_fit_says_so_when_no_rule_is_active(referral):
    body = api(referral["officer"]).get(referral["url"]).json()
    assert body["available"] is False and "No compatibility rule" in body["reason"]


def test_fit_says_so_when_the_youth_has_no_recorded_facts(referral):
    activate_compatibility()
    ParticipantQualification.objects.all().delete()
    ParticipantSkill.objects.all().delete()
    body = api(referral["officer"]).get(referral["url"]).json()
    assert body["available"] is False and "recorded" in body["reason"]


def test_fit_follows_the_referral_scope_and_permission(referral, make_user):
    activate_compatibility()
    outsider = make_user("other", "Placement officer")
    identity.set_scopes(actor=None, user=outsider, scopes=[("officer", "self")])
    assert api(outsider).get(referral["url"]).status_code == 404  # outside the caseload
    assert api(make_user("analyst", "M&E analyst")).get(referral["url"]).status_code == 403
    assert Client().get(referral["url"]).status_code in (401, 403)


def test_referral_detail_tells_the_page_whether_the_profile_may_be_opened(referral):
    body = api(referral["officer"]).get(f"/api/v1/referrals/{referral['ref'].pk}").json()
    assert body["can"]["view_profile"] is True
