"""Module A: support flags and the review queue, from facts PI 360 already holds."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.employers.models import Employer, Opportunity
from apps.intelligence import services
from apps.participants.models import Participant, ParticipantReadiness
from apps.referrals.models import Referral, StageEvent

from .test_participants import enrol, world  # noqa: F401

URL = "/api/v1/support/queue"


def api(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def opp(db):
    return Opportunity.objects.create(
        employer=Employer.objects.create(name="Acme"), title="Cook", status="open"
    )


def youth(name):
    return Participant.objects.create(full_name_source=name)


def refer(p, opp, stage, *, days_ago=5):
    when = timezone.now() - timedelta(days=days_ago)
    r = Referral.objects.create(
        participant=p, opportunity=opp, stage=stage, referred_at=when - timedelta(days=1)
    )
    StageEvent.objects.create(
        referral=r, from_stage="submitted", to_stage=stage, at=when, actor_label="t"
    )
    Referral.objects.filter(pk=r.pk).update(updated_at=when)
    return r


def queue(user):
    return api(user).get(URL).json()


def test_repeated_unsuccessful_referrals_raise_a_flag_with_the_count(opp, make_user):
    a, b = youth("Two Rejections"), youth("One Rejection")
    refer(a, opp, "rejected")
    refer(a, opp, "no_response")
    refer(b, opp, "rejected")
    body = queue(make_user("admin", "Administrator"))
    names = {i["name"]: i for i in body["items"]}
    assert "One Rejection" not in names
    flag = names["Two Rejections"]["flags"][0]
    assert flag["code"] == "unsuccessful" and "2 unsuccessful" in flag["detail"]


def test_the_number_is_a_setting_the_admin_can_change(opp, make_user):
    a = youth("One Rejection")
    refer(a, opp, "rejected")
    admin = make_user("admin", "Administrator")
    assert queue(admin)["items"] == []
    services.update_settings(actor=admin, values={"support.unsuccessful": 1})
    assert [i["name"] for i in queue(admin)["items"]] == ["One Rejection"]


def test_an_open_referral_that_stops_moving_is_flagged_but_a_recent_one_is_not(opp, make_user):
    stuck, fine = youth("Stuck"), youth("Moving")
    refer(stuck, opp, "under_review", days_ago=70)
    refer(fine, opp, "under_review", days_ago=10)
    items = queue(make_user("admin", "Administrator"))["items"]
    assert [i["name"] for i in items] == ["Stuck"]
    assert items[0]["flags"][0]["code"] == "stalled" and items[0]["longest_days"] >= 70


def test_ready_but_never_referred_needs_availability_and_enrollment(world, opp, make_user):  # noqa: F811
    waiting, no_date = youth("Waiting"), youth("No Date")
    other = youth("Referred")
    for p in (waiting, no_date, other):
        enrol(world, p).__class__.objects.filter(participant=p).update(status="enrolled")
    since = timezone.localdate() - timedelta(days=45)
    ParticipantReadiness.objects.create(participant=waiting, available_from=since)
    ParticipantReadiness.objects.create(participant=other, available_from=since)
    ParticipantReadiness.objects.create(participant=no_date)
    refer(other, opp, "submitted", days_ago=1)
    items = queue(make_user("admin", "Administrator"))["items"]
    assert [i["name"] for i in items] == ["Waiting"]
    assert items[0]["flags"][0]["code"] == "unreferred"


def test_reviewing_pauses_the_flag_and_is_audited(opp, make_user):
    a = youth("Two Rejections")
    refer(a, opp, "rejected")
    refer(a, opp, "rejected")
    admin = make_user("admin", "Administrator")
    c = api(admin)
    url = f"/api/v1/participants/{a.pk}/support-review"
    bad = c.post(url, {"outcome": "no_action"}, content_type="application/json")
    assert bad.status_code == 400  # a reason is needed when nothing was done
    ok = c.post(
        url,
        {"outcome": "contacted", "note": "Called", "flags": ["unsuccessful"]},
        content_type="application/json",
    )
    assert ok.status_code == 204
    body = queue(admin)
    assert body["items"] == [] and body["counts"]["paused"] == 1
    from apps.audit.models import AuditEvent

    assert AuditEvent.objects.filter(action="support_review.create").count() == 1


def test_scope_and_permissions(opp, make_user):
    a = youth("Two Rejections")
    refer(a, opp, "rejected")
    refer(a, opp, "rejected")
    officer = make_user("amina", "Placement officer")
    assert queue(officer)["items"] == []  # empty caseload
    assert api(make_user("analyst", "M&E analyst")).get(URL).status_code == 403
    assert Client().get(URL).status_code in (401, 403)
    nope = api(officer).post(
        f"/api/v1/participants/{a.pk}/support-review",
        {"outcome": "contacted"},
        content_type="application/json",
    )
    assert nope.status_code == 404  # outside the officer's scope
    assert "Missing documents" in queue(make_user("admin", "Administrator"))["not_captured"][0]
