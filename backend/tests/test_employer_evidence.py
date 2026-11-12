"""Module C evidence: counts, period and source, with 'insufficient evidence' under the minimum."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.employers.models import Employer, Opportunity
from apps.intelligence import services
from apps.participants.models import Participant
from apps.referrals.models import Referral, StageEvent


def api(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def employer(db):
    return Employer.objects.create(name="Acme")


def refer(employer, n, *, replied=0, interview=0, placed=0, age_days=10):
    opp = Opportunity.objects.create(employer=employer, title="Cook", status="open")
    now = timezone.now()
    for i in range(n):
        r = Referral.objects.create(
            participant=Participant.objects.create(full_name_source=f"Y{i}{n}{age_days}"),
            opportunity=opp,
            stage=Referral.SUBMITTED,
            referred_at=now - timedelta(days=age_days),
        )
        if i < replied:
            StageEvent.objects.create(
                referral=r, from_stage="submitted", to_stage="under_review",
                at=r.referred_at + timedelta(days=2), actor_label="t",
            )  # fmt: skip
        if i < interview:
            StageEvent.objects.create(
                referral=r, from_stage="under_review", to_stage="interview",
                at=now, actor_label="t",
            )  # fmt: skip
        if i < placed:
            StageEvent.objects.create(
                referral=r, from_stage="selected", to_stage="placed", at=now, actor_label="t"
            )


def test_under_the_minimum_says_insufficient_evidence(employer, make_user):
    refer(employer, 3, replied=3)
    body = api(make_user("admin", "Administrator")).get(
        f"/api/v1/employers/{employer.pk}/evidence"
    ).json()  # fmt: skip
    assert body["enough"] is False and "Insufficient evidence" in body["summary"]
    assert body["referrals_in_period"] == 3 and body["minimum_referrals"] == 5
    answered = body["indicators"][0]
    assert answered["text"] == "3 of 3 referrals got a reply" and answered["percent"] is None
    assert answered["status"] == "insufficient" and answered["source"] == "PI 360 referrals"
    assert {i["status"] for i in body["indicators"][-2:]} == {"no_data"}


def test_enough_referrals_show_counts_and_the_minimum_is_a_setting(employer, make_user):
    refer(employer, 4, replied=2, interview=1, placed=1)
    c = api(make_user("admin", "Administrator"))
    url = f"/api/v1/employers/{employer.pk}/evidence"
    assert c.get(url).json()["enough"] is False
    services.update_settings(actor=None, values={"employer.min_referrals": 4})
    body = c.get(url).json()
    assert body["enough"] is True
    by = {i["label"]: i for i in body["indicators"]}
    assert by["Referrals answered"]["percent"] == 50
    assert by["Interviews"]["count"] == 1 and by["Placements"]["count"] == 1
    assert by["Typical time to reply"]["text"].startswith("2.0 days")


def test_old_referrals_fall_outside_the_period(employer, make_user):
    refer(employer, 6, age_days=400)
    body = api(make_user("admin", "Administrator")).get(
        f"/api/v1/employers/{employer.pk}/evidence"
    ).json()  # fmt: skip
    assert body["referrals_in_period"] == 0 and body["enough"] is False


def test_unknown_employer_is_404_and_needs_permission(db, make_user):
    missing = f"/api/v1/employers/{'0' * 8}-0000-0000-0000-{'0' * 12}/evidence"
    assert api(make_user("admin", "Administrator")).get(missing).status_code == 404
    assert Client().get(missing).status_code in (401, 403)
