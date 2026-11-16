"""Dashboard (T-070): every number is the length of the list behind it, scope applies to both."""

from datetime import date, timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.employers.models import Employer, Opportunity
from apps.participants.models import Participant
from apps.referrals.models import Referral, StageEvent

DASH = "/api/v1/reporting/dashboard"
DRILL = "/api/v1/reporting/drilldown"


def api(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def opp(db):
    emp = Employer.objects.create(name="Acme")
    return Opportunity.objects.create(
        employer=emp,
        title="Cook",
        status="open",
        closing_date=date.today() + timedelta(days=5),
    )


def youth(name, gender="female"):
    return Participant.objects.create(full_name_source=name, gender=gender)


def refer(p, opp, stage, *, days_ago=5):
    when = timezone.now() - timedelta(days=days_ago)
    r = Referral.objects.create(
        participant=p, opportunity=opp, stage=stage, referred_at=when - timedelta(days=3)
    )
    StageEvent.objects.create(
        referral=r, from_stage="submitted", to_stage=stage, at=when, actor_label="t"
    )
    Referral.objects.filter(pk=r.pk).update(updated_at=when)
    return r


def test_tiles_and_funnel(opp, make_user):
    a, b, c = youth("Ann"), youth("Bob", "male"), youth("Cy", "male")
    refer(a, opp, "placed")
    refer(b, opp, "rejected")
    d = api(make_user("admin", "Administrator")).get(DASH).json()
    t = d["tiles"]
    assert (t["registered"], t["referred"], t["placed"]) == (3, 2, 1)
    assert t["placement_rate"] == 33.3
    assert t["submitted"] == 2 and t["conversion"] == 50.0
    assert t["open_opportunities"] == 1 and t["active_employers"] == 1
    assert d["funnel"][2]["count"] == 1 and c  # Cy never referred
    assert {g["label"]: g["count"] for g in d["gender"]} == {"Female": 1, "Male": 2}
    assert len(d["recent"]["opportunities"]) == 1
    assert len(d["recent"]["referrals"]) == 2


def test_every_number_opens_the_list_it_counts(opp, make_user):
    for n in ("Ann", "Bob"):
        refer(youth(n), opp, "interview")
    refer(youth("Old"), opp, "interview", days_ago=200)
    client = api(make_user("admin", "Administrator"))
    d = client.get(DASH).json()
    for key, count in [
        ("youth.registered", 3),
        ("referrals.active", 3),
        ("referrals.overdue", 1),
        ("opportunities.closing_soon", 1),
    ]:
        body = client.get(DRILL, {"key": key}).json()
        assert body["total"] == count and len(body["results"]) == count
    tile = {a["key"]: a["count"] for a in d["alerts"]}
    assert tile["referrals.overdue"] == 1
    row = client.get(DRILL, {"key": "youth.registered"}).json()["results"][0]
    assert row["link"].startswith("/youth/") and row["name"] == "Ann"


def test_unknown_key_is_not_found(make_user, db):
    assert api(make_user("admin", "Administrator")).get(DRILL, {"key": "nope"}).status_code == 404


def test_sections_follow_the_viewers_permissions(opp, make_user):
    youth("Ann")
    # a youth-portal user can open the page but sees no counts: they hold no list permission
    d = api(make_user("youth", "Youth")).get(DASH).json()
    assert d["can"] == {"youth": False, "referrals": False, "employers": False}
    assert d["tiles"]["registered"] == 0 and d["tiles"]["open_opportunities"] == 0
    assert api(make_user("youth2", "Youth")).get(DRILL, {"key": "youth.registered"}).json()["total"] == 0  # fmt: skip


def test_period_limits_submitted_referrals_only(opp, make_user):
    refer(youth("Ann"), opp, "submitted", days_ago=5)
    refer(youth("Old"), opp, "submitted", days_ago=200)
    client = api(make_user("admin", "Administrator"))
    assert client.get(DASH, {"period": "30"}).json()["tiles"]["submitted"] == 1
    assert client.get(DASH, {"period": "all"}).json()["tiles"]["submitted"] == 2
    assert client.get(DASH, {"period": "30"}).json()["tiles"]["registered"] == 2
