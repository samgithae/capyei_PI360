"""Referral workflow (T-046, FR-16..FR-20). Synthetic data only.

Acceptance: an unsuccessful close needs a reason; corrections preserve history."""

from datetime import date, timedelta

import pytest
from django.test import Client

from apps.audit.models import AuditEvent
from apps.configuration.models import ReferralReason
from apps.employers.models import Employer, Opportunity
from apps.identity import services as identity
from apps.participants.models import Participant
from apps.referrals import services
from apps.referrals.models import AppendOnly, Referral, StageEvent

URL = "/api/v1/referrals"
JSON = "application/json"


@pytest.fixture
def opp(db):
    employer = Employer.objects.create(name="Acme Traders")
    return Opportunity.objects.create(
        employer=employer, title="Sales assistant", status=Opportunity.OPEN,
        closing_date=date.today() + timedelta(days=30),
    )  # fmt: skip


@pytest.fixture
def officer(make_user):
    """A placement officer who sees only the youth assigned to them."""
    user = make_user("wanjiru", "Placement officer")
    identity.set_scopes(actor=None, user=user, scopes=[("officer", "self")])
    return user


@pytest.fixture
def manager(make_user, officer):
    """A manager whose scope is that officer's caseload."""
    user = make_user("manager", "Manager")
    identity.set_scopes(actor=None, user=user, scopes=[("officer", str(officer.pk))])
    return user


@pytest.fixture
def youth(officer):
    return Participant.objects.create(full_name_source="Test Youth A", assigned_officer=officer)


@pytest.fixture
def stranger(db):
    return Participant.objects.create(full_name_source="Test Youth B")


def client_for(user):
    c = Client()
    c.force_login(user)
    return c


def reason(code):
    return str(ReferralReason.objects.get(code=code).pk)


def refer(c, youth, opp, **kw):
    body = {"participant_id": str(youth.pk), "opportunity_id": str(opp.pk), **kw}
    return c.post(URL, body, content_type=JSON)


def move(c, rid, to, **kw):
    return c.post(f"{URL}/{rid}/transition", {"to": to, **kw}, content_type=JSON)


def test_create_submits_and_records_history(officer, youth, opp):
    c = client_for(officer)
    r = refer(c, youth, opp, note="Strong sales attitude")
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["stage"] == "submitted"
    assert body["assigned_to_id"] == officer.pk
    assert [(h["from"], h["to"]) for h in body["history"]] == [
        ("", "draft"),
        ("draft", "submitted"),
    ]
    assert body["history"][0]["note"] == "Strong sales attitude"
    assert AuditEvent.objects.filter(action="referral.created").count() == 1


def test_draft_then_submit(officer, youth, opp):
    c = client_for(officer)
    rid = refer(c, youth, opp, submit=False).json()["id"]
    assert move(c, rid, "submitted").json()["stage"] == "submitted"
    assert Referral.objects.get(pk=rid).referred_at is not None


def test_only_open_opportunities_take_referrals(officer, youth, opp):
    opp.status = Opportunity.CLOSED
    opp.save()
    r = refer(client_for(officer), youth, opp)
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "opportunity_closed"


def test_one_open_referral_per_youth_and_opportunity(officer, youth, opp):
    c = client_for(officer)
    assert refer(c, youth, opp).status_code == 201
    r = refer(c, youth, opp)
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "duplicate"


def test_cannot_refer_youth_outside_scope(officer, stranger, opp):
    r = refer(client_for(officer), stranger, opp)
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "unknown_participant"


def test_referral_outside_scope_is_404(officer, make_user, stranger, opp):
    admin = client_for(make_user("lead", "Administrator"))  # whole-organisation scope
    rid = refer(admin, stranger, opp).json()["id"]
    assert admin.get(f"{URL}/{rid}").status_code == 200
    assert client_for(officer).get(f"{URL}/{rid}").status_code == 404
    assert client_for(officer).get(URL).json()["total"] == 0


def test_stage_model_is_enforced(officer, youth, opp):
    c = client_for(officer)
    rid = refer(c, youth, opp).json()["id"]
    r = move(c, rid, "placed")
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "bad_transition"


def test_happy_path_to_placed_and_closed(officer, youth, opp):
    c = client_for(officer)
    rid = refer(c, youth, opp).json()["id"]
    for to in ("under_review", "interview", "selected", "placed", "closed"):
        r = move(c, rid, to)
        assert r.status_code == 200, (to, r.content)
    body = r.json()
    assert body["stage"] == "closed"
    assert body["closed_at"]
    assert body["next_stages"] == []


def test_unsuccessful_outcome_needs_a_matching_reason(officer, youth, opp):
    c = client_for(officer)
    rid = refer(c, youth, opp).json()["id"]
    r = move(c, rid, "rejected")
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "reason_required"
    r = move(c, rid, "rejected", reason_id=reason("NOR-EMPLOYER"))
    assert r.json()["errors"][0]["code"] == "reason_mismatch"
    r = move(c, rid, "rejected", reason_id=reason("OTHER"))
    assert r.json()["errors"][0]["code"] == "note_required"
    r = move(c, rid, "rejected", reason_id=reason("REJ-SKILLS"))
    assert r.status_code == 200
    assert r.json()["reason"] == "Skills or qualification gap"


def test_unsuccessful_close_keeps_its_reason(officer, youth, opp):
    c = client_for(officer)
    rid = refer(c, youth, opp).json()["id"]
    move(c, rid, "withdrawn", reason_id=reason("WDR-DISTANCE"))
    body = move(c, rid, "closed").json()
    assert body["stage"] == "closed"
    assert body["reason"] == "Distance or transport cost"


def test_close_without_reason_is_refused_even_for_legacy_rows(officer, youth, opp):
    ref = services.create_referral(actor=officer, participant_id=youth.pk, opportunity_id=opp.pk)
    Referral.objects.filter(pk=ref.pk).update(stage=Referral.NO_RESPONSE)  # e.g. old data
    r = move(client_for(officer), ref.pk, "closed")
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "reason_required"


def test_correction_keeps_history_and_points_at_the_original(officer, youth, opp):
    c = client_for(officer)
    rid = refer(c, youth, opp).json()["id"]
    move(c, rid, "rejected", reason_id=reason("REJ-SKILLS"))
    wrong = StageEvent.objects.filter(referral_id=rid).latest("id")
    r = c.post(f"{URL}/{rid}/correct", {"to": "under_review"}, content_type=JSON)
    assert r.json()["errors"][0]["code"] == "note_required"
    r = c.post(
        f"{URL}/{rid}/correct",
        {"to": "under_review", "note": "Recorded against the wrong youth"},
        content_type=JSON,
    )
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["stage"] == "under_review"
    assert body["reason"] == ""
    kinds = [(h["kind"], h["to"]) for h in body["history"]]
    assert ("transition", "rejected") in kinds  # the original stays
    assert kinds[-1] == ("correction", "under_review")
    assert body["history"][-1]["corrects"] == wrong.pk
    assert AuditEvent.objects.filter(action="referral.corrected").count() == 1


def test_reopening_a_closed_referral_needs_approval(officer, manager, youth, opp):
    c = client_for(officer)
    rid = refer(c, youth, opp).json()["id"]
    move(c, rid, "no_response", reason_id=reason("NOR-EMPLOYER"))
    move(c, rid, "closed")
    body = {"to": "submitted", "note": "Employer replied late"}
    assert c.post(f"{URL}/{rid}/correct", body, content_type=JSON).status_code == 403
    r = client_for(manager).post(f"{URL}/{rid}/correct", body, content_type=JSON)
    assert r.status_code == 200, r.content
    assert r.json()["stage"] == "submitted"
    assert r.json()["closed_at"] is None


def test_stage_history_is_append_only(officer, youth, opp):
    ref = services.create_referral(actor=officer, participant_id=youth.pk, opportunity_id=opp.pk)
    event = ref.events.first()
    event.note = "rewritten"
    with pytest.raises(AppendOnly):
        event.save()
    with pytest.raises(AppendOnly):
        event.delete()
    with pytest.raises(AppendOnly):
        StageEvent.objects.filter(referral=ref).update(note="x")
    with pytest.raises(AppendOnly):
        StageEvent.objects.filter(referral=ref).delete()


def test_reassign_needs_caseload_permission(officer, manager, make_user, youth, opp):
    other = make_user("otieno", "Placement officer")
    rid = refer(client_for(officer), youth, opp).json()["id"]
    body = {"user_id": other.pk}
    r = client_for(officer).post(f"{URL}/{rid}/assign", body, content_type=JSON)
    assert r.status_code == 403
    manager = client_for(manager)
    assert manager.post(f"{URL}/{rid}/assign", body, content_type=JSON).json()[
        "assigned_to_id"
    ] == (other.pk)
    steward = make_user("steward", "Data steward")  # cannot work referrals
    r = manager.post(f"{URL}/{rid}/assign", {"user_id": steward.pk}, content_type=JSON)
    assert r.json()["errors"][0]["code"] == "bad_user"


def test_list_filters_and_summary(officer, youth, opp):
    c = client_for(officer)
    rid = refer(c, youth, opp).json()["id"]
    assert c.get(URL, {"stage": "active"}).json()["total"] == 1
    assert c.get(URL, {"stage": "closed"}).json()["total"] == 0
    assert c.get(URL, {"q": "Acme"}).json()["results"][0]["id"] == rid
    assert c.get(URL, {"mine": "1"}).json()["total"] == 1
    assert c.get(URL, {"participant": "nope"}).status_code == 400
    assert c.get(f"{URL}/summary").json()["submitted"] == 1


def test_reasons_are_filtered_by_outcome(officer):
    c = client_for(officer)
    codes = {r["code"] for r in c.get(f"{URL}/reasons", {"stage": "no_response"}).json()}
    assert codes == {"NOR-EMPLOYER", "NOR-YOUTH", "OTHER"}
