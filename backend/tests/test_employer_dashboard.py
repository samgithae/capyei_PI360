# ruff: noqa: F811, S105
"""Employer portal, phase 4: the dashboard.

What these prove: every figure equals the number of rows in the list it links to (one query serves
both), each role sees only the sections its permissions open, a company never sees another
company's numbers, and nothing staff-only appears."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.employers.models import Opportunity
from apps.referrals.models import Referral

from .test_employer_data import (  # noqa: F401
    P,
    _fresh_throttle,
    acme,
    admin,
    api,
    assert_clean,
    beta,
    boss_b,
    hr,
    new_opportunity,
    officer,
    refer,
    steward,
    viewer,
)
from .test_employer_portal import company_invite  # noqa: E402

OPP_VIEWS = ("open", "closing_soon", "expired", "awaiting", "declined")
REF_VIEWS = ("new", "review", "interviews", "selected", "placed_ytd", "replied", "waiting")


def day(n):
    return timezone.localdate() + timedelta(days=n)


@pytest.fixture
def busy(acme, officer):
    """A company with opportunities in every state and referrals at several stages."""
    # Referrals need a closing date in the future, so the date is cleared after referring.
    undated = new_opportunity(
        acme, title="Open no date", status=Opportunity.OPEN, closing_date=day(30)
    )
    new_opportunity(acme, title="Closing soon", status=Opportunity.OPEN, closing_date=day(3))
    # Referrals are refused once an opportunity is late, so it is referred while still in date.
    late = new_opportunity(acme, title="Late", status=Opportunity.OPEN, closing_date=day(5))
    new_opportunity(acme, title="Marked expired", status=Opportunity.EXPIRED)
    new_opportunity(
        acme, title="Awaiting", status=Opportunity.DRAFT, publish_requested_at=timezone.now()
    )
    new_opportunity(
        acme,
        title="Sent back",
        status=Opportunity.DRAFT,
        publish_declined_at=timezone.now(),
        publish_declined_reason="Add a closing date",
    )
    refer(officer, acme, "Youth One", "Open no date")
    refer(officer, acme, "Youth Two", "Open no date", stage=Referral.UNDER_REVIEW)
    refer(officer, acme, "Youth Three", "Closing soon", stage=Referral.UNDER_REVIEW)
    refer(officer, acme, "Youth Four", "Closing soon", stage=Referral.SELECTED)
    old = refer(officer, acme, "Youth Five", "Late")[2]
    Referral.objects.filter(pk=old.pk).update(referred_at=timezone.now() - timedelta(days=9))
    Opportunity.objects.filter(pk=late.pk).update(closing_date=day(-2))
    Opportunity.objects.filter(pk=undated.pk).update(closing_date=None)
    return acme


def get(user, path="dashboard", **params):
    r = api(user).get(f"{P}/{path}", params)
    assert r.status_code == 200, r.content
    return r.json()


def test_every_opportunity_figure_equals_its_list(admin, busy):
    figures = get(admin)["opportunities"]
    assert set(figures) == set(OPP_VIEWS)
    for view in OPP_VIEWS:
        listed = get(admin, "opportunities", view=view)
        assert listed["total"] == figures[view], view
    assert figures["open"] == 2 and figures["closing_soon"] == 1 and figures["expired"] == 2
    assert figures["awaiting"] == 1 and figures["declined"] == 1


def test_every_referral_figure_equals_its_list(admin, busy):
    data = get(admin)["referrals"]
    assert set(data["figures"]) == set(REF_VIEWS)
    for view in REF_VIEWS:
        listed = get(admin, "referrals", view=view)
        assert listed["total"] == data["figures"][view], view
    figures = data["figures"]
    assert figures["new"] == 2 and figures["review"] == 2 and figures["selected"] == 1
    assert figures["waiting"] == 1


def test_the_funnel_trend_and_per_opportunity_add_up(admin, busy):
    data = get(admin)["referrals"]
    assert sum(f["count"] for f in data["funnel"]) == 5
    assert len(data["trend"]) == 12 and sum(t["count"] for t in data["trend"]) == 5
    assert sum(o["total"] for o in data["per_opportunity"]) == 5
    first = data["per_opportunity"][0]
    listed = get(admin, "referrals", opportunity=first["opportunity_id"])
    assert listed["total"] == first["total"]


def test_attention_and_activity_point_at_real_lists(admin, busy):
    body = get(admin)
    kinds = {a["kind"] for a in body["attention"]}
    assert {"waiting", "closing", "expired", "declined"} <= kinds
    for item in (*body["attention"], *body["activity"]):
        assert item["link"].startswith("/employer/") and item["text"]
    waiting = next(a for a in body["attention"] if a["kind"] == "waiting")
    assert waiting["link"] == "/employer/referrals?view=waiting" and waiting["count"] == 1


def test_a_pending_invite_is_flagged_to_the_admin_only(admin, hr):
    assert company_invite(admin, "new@acme.example").status_code == 201
    body = get(admin)
    assert any(a["kind"] == "invites" and a["count"] == 1 for a in body["attention"])
    assert any(a["kind"] == "invite" for a in body["activity"])
    assert get(hr)["can"]["team"] is False
    assert not any(a["kind"] == "invites" for a in get(hr)["attention"])


def test_each_role_sees_only_the_sections_it_may_open(admin, hr, viewer, busy):
    assert get(admin)["can"] == {"opportunities": True, "referrals": True, "team": True}
    seen = get(hr)
    assert seen["can"]["opportunities"] and seen["can"]["referrals"] and not seen["can"]["team"]
    assert "referrals" in get(viewer) and "opportunities" in get(viewer)


def test_a_company_sees_none_of_another_companys_numbers(admin, boss_b, busy):
    other = get(boss_b)
    assert other["opportunities"] == dict.fromkeys(OPP_VIEWS, 0)
    assert all(v == 0 for v in other["referrals"]["figures"].values())
    assert other["referrals"]["per_opportunity"] == [] and other["activity"] == []
    assert get(boss_b, "opportunities")["total"] == 0


def test_nothing_staff_only_is_in_the_dashboard(admin, busy):
    assert_clean(api(admin).get(f"{P}/dashboard"), "notes")


def test_an_unknown_view_is_ignored_rather_than_failing(admin, busy):
    assert get(admin, "referrals", view="nonsense")["total"] == 5
    assert get(admin, "opportunities", view="nonsense")["total"] == 6


def test_the_dashboard_needs_signing_in_and_the_permission(officer, make_user):
    from django.test import Client

    assert Client().get(f"{P}/dashboard").status_code in (401, 403)
    assert api(officer).get(f"{P}/dashboard").status_code == 403
