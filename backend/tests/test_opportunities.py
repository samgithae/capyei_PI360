"""Opportunity management (T-045, FR-12..FR-15). Synthetic data only."""

from datetime import date, timedelta

import pytest
from django.core.management import call_command
from django.test import Client

from apps.employers import services
from apps.employers.models import Employer, Opportunity

URL = "/api/v1/opportunities"
JSON = "application/json"
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture
def c(make_user):
    cl = Client()
    cl.force_login(make_user("steward", "Data steward"))
    return cl


@pytest.fixture
def employer(db):
    return Employer.objects.create(name="Acme Traders")


def new(c, employer, **kw):
    body = {"employer_id": str(employer.pk), "title": "Sales assistant", **kw}
    return c.post(URL, body, content_type=JSON)


def move(c, opp_id, to):
    return c.post(f"{URL}/{opp_id}/transition", {"to": to}, content_type=JSON)


def test_create_defaults_to_draft_and_validates(c, employer):
    r = new(c, employer, positions=3)
    assert r.status_code == 201 and r.json()["status"] == "draft" and r.json()["positions"] == 3
    assert new(c, employer, positions=0).status_code == 400
    assert new(c, employer, start_date=TOMORROW, closing_date=YESTERDAY).status_code == 409
    employer.status = "inactive"
    employer.save()
    assert new(c, employer).json()["errors"][0]["code"] == "employer_inactive"


def test_state_machine(c, employer):
    oid = new(c, employer).json()["id"]
    assert move(c, oid, "closed").status_code == 409  # draft cannot close
    r = move(c, oid, "open")  # no closing date
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "closing_date"
    c.patch(f"{URL}/{oid}", {"closing_date": TOMORROW}, content_type=JSON)
    assert move(c, oid, "open").json()["status"] == "open"
    assert move(c, oid, "closed").json()["status"] == "closed"
    assert move(c, oid, "open").json()["status"] == "open"  # reopen
    assert (
        c.post(f"{URL}/{oid}/transition", {"to": "expired"}, content_type=JSON).status_code == 400
    )
    actions = [e["action"] for e in c.get(f"{URL}/{oid}/history").json()]
    assert actions[:3] == ["opportunity.open", "opportunity.closed", "opportunity.open"]


def test_closed_opportunity_is_locked_and_blocks_referrals(c, employer):
    oid = new(c, employer, closing_date=TOMORROW).json()["id"]
    move(c, oid, "open")
    assert services.accepts_referrals(oid)
    move(c, oid, "closed")
    assert not services.accepts_referrals(oid)
    assert c.patch(f"{URL}/{oid}", {"title": "x"}, content_type=JSON).status_code == 409
    r = c.post(
        f"{URL}/{oid}/requirements", {"factor": "skill", "description": "x"}, content_type=JSON
    )
    assert r.status_code == 409


def test_scheduled_expiry_is_idempotent(c, employer):
    oid = new(c, employer, closing_date=TOMORROW).json()["id"]
    move(c, oid, "open")
    Opportunity.objects.filter(pk=oid).update(closing_date=date.today() - timedelta(days=1))
    assert not services.accepts_referrals(oid)  # past closing blocks even before the job runs
    call_command("expire_opportunities")
    assert Opportunity.objects.get(pk=oid).status == "expired"
    assert services.expire_due() == 0
    assert c.get(f"{URL}/{oid}/history").json()[0]["actor"] == "system"
    # expired can be reopened only with a future date
    assert move(c, oid, "open").status_code == 409
    c.patch(f"{URL}/{oid}", {"closing_date": TOMORROW}, content_type=JSON)  # locked while expired
    Opportunity.objects.filter(pk=oid).update(closing_date=date.today() + timedelta(days=5))
    assert move(c, oid, "open").json()["status"] == "open"


def test_requirements_mandatory_and_preferred(c, employer):
    oid = new(c, employer).json()["id"]
    base = f"{URL}/{oid}/requirements"
    a = c.post(
        base,
        {"factor": "qualification", "description": "Certificate", "is_mandatory": True},
        content_type=JSON,
    )
    b = c.post(base, {"factor": "skill", "description": "Cashier"}, content_type=JSON)
    assert a.status_code == b.status_code == 201 and b.json()["is_mandatory"] is False
    assert (
        c.post(base, {"factor": "hair", "description": "x"}, content_type=JSON).status_code == 400
    )
    reqs = c.get(f"{URL}/{oid}").json()["requirements"]
    assert [r["is_mandatory"] for r in reqs] == [True, False]
    r = c.patch(f"{base}/{b.json()['id']}", {"is_mandatory": True}, content_type=JSON)
    assert r.json()["is_mandatory"] is True
    assert c.delete(f"{base}/{a.json()['id']}").status_code == 204
    assert c.delete(f"{base}/{a.json()['id']}").status_code == 404


def test_list_filters(c, employer):
    new(c, employer, title="Barista")
    other = new(c, employer, title="Intern", kind="internship").json()["id"]
    assert c.get(URL).json()["total"] == 2
    assert c.get(URL, {"q": "bar"}).json()["total"] == 1
    assert c.get(URL, {"kind": "internship"}).json()["results"][0]["id"] == other
    assert c.get(URL, {"employer": str(employer.pk)}).json()["total"] == 2
    assert c.get(URL, {"employer": "bad"}).status_code == 400


def test_expiry_only_touches_open_opportunities_past_their_date(employer):
    today = date.today()
    mk = lambda status, closing: Opportunity.objects.create(  # noqa: E731
        employer=employer, title=status, status=status, closing_date=closing
    )
    due = mk("open", today - timedelta(days=1))
    last_day = mk("open", today)  # still open on its closing day
    draft = mk("draft", today - timedelta(days=9))
    closed = mk("closed", today - timedelta(days=9))
    assert services.expire_due() == 1
    assert services.expire_due(today=today + timedelta(days=1)) == 1  # closing day has passed
    for o, want in ((due, "expired"), (last_day, "expired"), (draft, "draft"), (closed, "closed")):
        assert Opportunity.objects.get(pk=o.pk).status == want


def test_typed_requirements_are_validated_described_and_flagged(c, employer):
    from apps.configuration.models import QualificationLevel, Skill

    oid = new(c, employer).json()["id"]
    base = f"{URL}/{oid}/requirements"
    diploma = QualificationLevel.objects.get(code="QL05")
    cook = Skill.objects.get(code="SK-FOOD")
    a = c.post(
        base,
        {
            "factor": "qualification",
            "qualification_level_id": str(diploma.pk),
            "is_mandatory": True,
        },
        content_type=JSON,
    ).json()
    assert a["description"] == f"{diploma.name} or higher" and not a["needs_structuring"]
    s = c.post(base, {"factor": "skill", "skill_id": str(cook.pk)}, content_type=JSON).json()
    assert s["description"] == cook.name and s["skill_id"] == str(cook.pk)
    e = c.post(base, {"factor": "experience", "min_months": 12}, content_type=JSON).json()
    assert e["description"] == "At least 12 months of experience"
    v = c.post(
        base,
        {"factor": "availability", "needed_by": "2027-01-10", "work_pattern": "shift"},
        content_type=JSON,
    ).json()
    assert "shift work" in v["description"] and v["needed_by"] == "2027-01-10"
    # Old free text still saves, but is flagged because nothing can be compared yet.
    old = c.post(base, {"factor": "skill", "description": "Good with people"}, content_type=JSON)
    assert old.status_code == 201 and old.json()["needs_structuring"] is True
    # Location and "other" are descriptive, never "needs structuring".
    loc = c.post(base, {"factor": "location", "description": "Near Westlands"}, content_type=JSON)
    assert loc.json()["needs_structuring"] is False
    # Bad input.
    bad = c.post(
        base,
        {"factor": "skill", "skill_id": "00000000-0000-0000-0000-000000000000"},
        content_type=JSON,
    )
    assert bad.status_code == 409
    assert c.post(base, {"factor": "experience"}, content_type=JSON).status_code == 409
    bp = c.post(base, {"factor": "availability", "work_pattern": "moon"}, content_type=JSON)
    assert bp.status_code == 409
    # Changing the factor clears values that no longer apply.
    r = c.patch(
        f"{base}/{e['id']}",
        {"factor": "skill", "skill_id": str(cook.pk), "description": ""},
        content_type=JSON,
    ).json()
    assert r["min_months"] is None and r["skill_id"] == str(cook.pk)
