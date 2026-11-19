"""Module C evidence: counts, period and source, with 'insufficient evidence' under the minimum."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.employers.models import Employer, Opportunity
from apps.intelligence import services
from apps.participants.models import Participant
from apps.placements.models import FollowUp, FollowUpStep, Placement
from apps.referrals.models import Referral, StageEvent

from .test_participants import enrol, world  # noqa: F401


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


# --- Retention after placement, read from the follow-up schedule (D-028) ---


@pytest.fixture
def schedule(db):
    FollowUpStep.objects.all().delete()
    return {
        "30": FollowUpStep.objects.create(kind="early", label="30 days", offset_days=30),
        "90": FollowUpStep.objects.create(kind="early", label="90 days", offset_days=90),
        "6m": FollowUpStep.objects.create(kind="tracer", label="6 months", offset_days=183),
    }


def checkin(world, employer, step, *, status="done", employed=True, due_ago=5, i=0):  # noqa: F811
    """One placement with this employer and its follow-up for ``step``."""
    youth = Participant.objects.create(full_name_source=f"R{step.offset_days}{i}{status}")
    placement = Placement.objects.create(
        enrollment=enrol(world, youth), employer=employer, status="placed", pathway="wage",
        start_date=timezone.localdate() - timedelta(days=step.offset_days + due_ago),
    )  # fmt: skip
    return FollowUp.objects.create(
        placement=placement, step=step, kind=step.kind, label=step.label, status=status,
        due_date=timezone.localdate() - timedelta(days=due_ago),
        still_employed=employed if status == "done" else None,
        evidence_source="phone_call" if status == "done" else "",
    )  # fmt: skip


def retention(client, employer):
    body = client.get(f"/api/v1/employers/{employer.pk}/evidence").json()
    return {i["label"]: i for i in body["indicators"]}["Retention after placement"]


def test_retention_uses_the_latest_early_step_and_counts_only_checked(
    employer,
    make_user,
    schedule,
    world,  # noqa: F811
):
    services.update_settings(actor=None, values={"employer.min_retention_checks": 3})
    for i in range(2):
        checkin(world, employer, schedule["90"], employed=True, i=i)
    checkin(world, employer, schedule["90"], employed=False, i=2)
    checkin(world, employer, schedule["90"], status="open", i=3)  # due, not checked yet
    checkin(world, employer, schedule["90"], status="unreachable", i=4)
    checkin(world, employer, schedule["30"], employed=False, i=5)  # the 30-day step is not it
    checkin(world, employer, schedule["6m"], employed=False, i=6)  # tracer, not it
    r = retention(api(make_user("admin", "Administrator")), employer)
    assert (r["count"], r["of"], r["status"], r["percent"]) == (2, 3, "shown", 67)
    assert r["text"] == (
        "2 of 3 placements checked at 90 days were still in the placement (2 due, not yet checked)"
    )


def test_retention_follows_the_schedule_when_the_point_moves(
    employer,
    make_user,
    schedule,
    world,  # noqa: F811
):
    services.update_settings(actor=None, values={"employer.min_retention_checks": 1})
    checkin(world, employer, schedule["30"], employed=True)
    c = api(make_user("admin", "Administrator"))
    assert retention(c, employer)["status"] == "no_data"  # the point is 90 days: nothing due
    schedule["90"].active = False
    schedule["90"].save()
    assert retention(c, employer)["text"].startswith("1 of 1 placements checked at 30 days")


def test_retention_under_the_minimum_or_outside_the_period_shows_no_percentage(
    employer,
    make_user,
    schedule,
    world,  # noqa: F811
):
    c = api(make_user("admin", "Administrator"))
    assert retention(c, employer)["status"] == "no_data"  # nothing due at all
    checkin(world, employer, schedule["90"], employed=True)
    r = retention(c, employer)
    assert r["status"] == "insufficient" and r["percent"] is None and r["count"] == 1
    checkin(world, employer, schedule["90"], employed=True, due_ago=400, i=1)  # before the period
    assert retention(c, employer)["of"] == 1


def test_retention_has_its_own_minimum_apart_from_referrals(
    employer,
    make_user,
    schedule,
    world,  # noqa: F811
):
    services.update_settings(
        actor=None, values={"employer.min_referrals": 50, "employer.min_retention_checks": 2}
    )
    c = api(make_user("admin", "Administrator"))
    checkin(world, employer, schedule["90"], employed=True, i=0)
    assert retention(c, employer)["percent"] is None
    checkin(world, employer, schedule["90"], employed=False, i=1)
    r = retention(c, employer)
    assert (r["status"], r["percent"]) == ("shown", 50)


def test_cancelled_and_other_employers_check_ins_are_left_out(
    employer,
    make_user,
    schedule,
    world,  # noqa: F811
):
    services.update_settings(actor=None, values={"employer.min_retention_checks": 1})
    checkin(world, employer, schedule["90"], status="cancelled", i=0)
    checkin(world, Employer.objects.create(name="Other"), schedule["90"], employed=True, i=1)
    assert retention(api(make_user("admin", "Administrator")), employer)["status"] == "no_data"
