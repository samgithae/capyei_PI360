"""Case management (T-064, T-065, FR-21..FR-24). Synthetic data only.

Acceptance: overdue interventions are flagged and the queue counts reconcile with the lists; a
new placement episode never overwrites an earlier one."""

from datetime import date, timedelta

import pytest
from django.test import Client

from apps.audit.models import AuditEvent
from apps.employers.models import Employer
from apps.identity import services as identity
from apps.participants.models import Participant
from apps.placements.models import Placement
from apps.referrals.models import Intervention

from .test_participants import enrol, world  # noqa: F401

JSON = "application/json"
IV = "/api/v1/interventions"
PL = "/api/v1/placements"


@pytest.fixture
def officer(make_user):
    user = make_user("wanjiru", "Placement officer")
    identity.set_scopes(actor=None, user=user, scopes=[("officer", "self")])
    return user


@pytest.fixture
def manager(make_user, officer):
    user = make_user("manager", "Manager")
    identity.set_scopes(actor=None, user=user, scopes=[("officer", str(officer.pk))])
    return user


@pytest.fixture
def youth(officer):
    return Participant.objects.create(full_name_source="Test Youth A", assigned_officer=officer)


@pytest.fixture
def stranger(db):
    return Participant.objects.create(full_name_source="Test Youth B")


@pytest.fixture
def enrollment(world, youth):  # noqa: F811
    return enrol(world, youth)


def client_for(user):
    c = Client()
    c.force_login(user)
    return c


def make_iv(c, youth, **kw):
    body = {"participant_id": str(youth.pk), "need": "cv_documents", "title": "Fix the CV", **kw}
    return c.post(IV, body, content_type=JSON)


# --- interventions ----------------------------------------------------------------------------


def test_create_assigns_the_actor_and_audits(officer, youth):
    r = make_iv(client_for(officer), youth)
    assert r.status_code == 201
    assert r.json()["status"] == "open" and r.json()["owner_id"] == officer.pk
    assert AuditEvent.objects.filter(action="intervention.created").count() == 1


def test_out_of_scope_youth_is_not_found(officer, stranger):
    c = client_for(officer)
    assert make_iv(c, stranger).status_code == 409
    other = Intervention.objects.create(participant=stranger, need="other", title="x")
    assert c.get(f"{IV}/{other.pk}").status_code == 404
    assert c.get(IV).json()["total"] == 0


def test_needs_a_title_a_known_need_and_a_future_due_date(officer, youth):
    c = client_for(officer)
    assert make_iv(c, youth, need="nonsense").status_code == 400
    assert make_iv(c, youth, title="  ").status_code in (400, 409)
    past = (date.today() - timedelta(days=1)).isoformat()
    assert make_iv(c, youth, due_date=past).status_code == 409


def test_closing_needs_a_verification_source_and_goes_through_the_steps(officer, youth):
    c = client_for(officer)
    pk = make_iv(c, youth).json()["id"]
    move = lambda **b: c.post(f"{IV}/{pk}/move", b, content_type=JSON)  # noqa: E731
    assert move(to="closed").status_code == 409  # cannot skip ahead
    assert move(to="in_progress").status_code == 200
    assert move(to="awaiting_verification").status_code == 200
    r = move(to="closed")
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "verification_required"
    r = move(to="closed", verification_source="phone_call", note="Spoke to the youth")
    assert r.status_code == 200 and r.json()["status"] == "closed"
    assert r.json()["closed_at"] and not r.json()["can"]["edit"]
    assert move(to="open").status_code == 409  # closed is final
    patch = c.patch(f"{IV}/{pk}", {"title": "again"}, content_type=JSON)
    assert patch.status_code == 409


def test_cancelling_needs_a_reason(officer, youth):
    c = client_for(officer)
    pk = make_iv(c, youth).json()["id"]
    r = c.post(f"{IV}/{pk}/move", {"to": "cancelled"}, content_type=JSON)
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "note_required"
    r = c.post(f"{IV}/{pk}/move", {"to": "cancelled", "note": "Youth moved"}, content_type=JSON)
    assert r.status_code == 200


def test_follow_up_links_to_its_parent(officer, youth):
    c = client_for(officer)
    pk = make_iv(c, youth).json()["id"]
    r = c.post(
        IV, {"follow_up_of_id": pk, "need": "mentoring", "title": "Check in"}, content_type=JSON
    )
    assert r.status_code == 201 and r.json()["follow_up_of_id"] == pk
    assert r.json()["participant_id"] == str(youth.pk)
    assert len(c.get(f"{IV}/{pk}").json()["follow_ups"]) == 1


def test_only_the_manager_reassigns_and_the_new_owner_must_work_cases(
    officer, manager, make_user, youth
):
    pk = make_iv(client_for(officer), youth).json()["id"]
    assert (
        client_for(officer)
        .post(f"{IV}/{pk}/assign", {"owner_id": officer.pk}, content_type=JSON)
        .status_code
        == 403
    )
    other = make_user("otto", "Placement officer")
    m = client_for(manager)
    r = m.post(f"{IV}/{pk}/assign", {"owner_id": other.pk}, content_type=JSON)
    assert r.status_code == 200 and r.json()["owner_id"] == other.pk
    assert AuditEvent.objects.filter(action="intervention.assigned").exists()
    viewer = make_user("viewer", "Manager")
    r = m.post(f"{IV}/{pk}/assign", {"owner_id": viewer.pk}, content_type=JSON)
    assert r.status_code == 409  # a manager does not hold referrals.edit


def test_a_manager_can_read_but_not_write(manager, officer, youth):
    pk = make_iv(client_for(officer), youth).json()["id"]
    m = client_for(manager)
    assert m.get(f"{IV}/{pk}").status_code == 200
    assert make_iv(m, youth).status_code == 403


# --- the work queue -----------------------------------------------------------------------


def test_queue_flags_overdue_first_and_counts_reconcile(officer, youth):
    today = date.today()
    mk = lambda t, due: Intervention.objects.create(  # noqa: E731
        participant=youth, need="other", title=t, owner=officer, due_date=due
    )
    mk("later", today + timedelta(days=20))
    mk("late", today - timedelta(days=3))
    mk("soon", today + timedelta(days=2))
    mk("undated", None)
    done = mk("done", today - timedelta(days=9))
    done.status = Intervention.CLOSED
    done.save()
    q = client_for(officer).get("/api/v1/cases/queue").json()
    items = q["interventions"]
    assert [i["title"] for i in items] == ["late", "soon", "later", "undated"]
    assert items[0]["overdue"] and not items[1]["overdue"]
    c = q["counts"]
    assert c["live"] == len(items) == 4
    assert c["overdue"] == sum(i["overdue"] for i in items) == 1
    assert c["due_soon"] == 1


def test_queue_mine_filters_to_the_callers_work(officer, manager, youth):
    Intervention.objects.create(participant=youth, need="other", title="mine", owner=officer)
    Intervention.objects.create(participant=youth, need="other", title="theirs", owner=None)
    c = client_for(officer)
    assert c.get("/api/v1/cases/queue?mine=1").json()["counts"]["live"] == 1
    assert c.get("/api/v1/cases/queue?mine=0").json()["counts"]["live"] == 2


# --- placements -----------------------------------------------------------------------------


def place(c, youth, **kw):
    body = {
        "participant_id": str(youth.pk), "pathway": "wage",
        "start_date": "2026-03-01", "employer_name_source": "Acme Traders", **kw,
    }  # fmt: skip
    return c.post(PL, body, content_type=JSON)


def test_a_new_episode_never_overwrites_an_earlier_one(officer, youth, enrollment):
    c = client_for(officer)
    first = place(c, youth)
    assert first.status_code == 201, first.content
    assert first.json()["current"] and not first.json()["verified"]
    ended = c.post(
        f"{PL}/{first.json()['id']}/end",
        {"end_date": "2026-06-01", "exit_reason": "Contract finished"}, content_type=JSON,
    )  # fmt: skip
    assert ended.status_code == 200 and not ended.json()["current"]
    second = place(c, youth, start_date="2026-07-01", employer_name_source="Beta Ltd")
    assert second.status_code == 201
    rows = c.get(f"{PL}?participant={youth.pk}").json()["results"]
    assert len(rows) == 2
    old = Placement.objects.get(pk=first.json()["id"])
    assert old.employer_name_source == "Acme Traders" and old.end_date == date(2026, 6, 1)
    assert sum(r["current"] for r in rows) == 1  # derived: only the running one counts


def test_verify_records_how_and_editing_clears_it(officer, youth, enrollment):
    c = client_for(officer)
    pk = place(c, youth).json()["id"]
    assert c.post(f"{PL}/{pk}/verify", {"source": "bogus"}, content_type=JSON).status_code == 400
    r = c.post(f"{PL}/{pk}/verify", {"source": "phone_call"}, content_type=JSON)
    assert r.status_code == 200 and r.json()["verified"] and r.json()["verified_on"]
    r = c.patch(f"{PL}/{pk}", {"designation": "Cashier"}, content_type=JSON)
    assert r.status_code == 200 and not r.json()["verified"]
    actions = set(AuditEvent.objects.filter(object_id=pk).values_list("action", flat=True))
    assert {"placement.verified", "placement.updated"} <= actions
    assert len(c.get(f"{PL}/{pk}/history").json()) >= 3


def test_end_date_cannot_precede_the_start(officer, youth, enrollment):
    c = client_for(officer)
    pk = place(c, youth).json()["id"]
    r = c.post(f"{PL}/{pk}/end", {"end_date": "2026-02-01"}, content_type=JSON)
    assert r.status_code == 409
    assert c.get(f"{PL}/{pk}").json()["current"]


def test_placement_scope_and_filters(officer, youth, stranger, enrollment, world):  # noqa: F811
    other = enrol(world, stranger)
    from apps.placements import services as placements

    placements.record(actor=None, enrollment_id=other.pk, source_status="Employment")
    c = client_for(officer)
    place(c, youth)
    place(c, youth, pathway="self_employment", employer_name_source="Own stall")
    body = c.get(PL).json()
    assert body["total"] == 2  # the stranger's episode is out of scope
    assert c.get(f"{PL}?pathway=self_employment").json()["total"] == 1
    assert c.get(f"{PL}?q=Test Youth").json()["total"] == 2  # search by youth name
    assert c.get(f"{PL}?q=Acme").json()["total"] == 1
    assert c.get(f"{PL}?state=unverified").json()["total"] == 2
    s = c.get(f"{PL}/summary").json()
    assert (
        s["total"] == 2 and s["current"] == 2 and s["by_pathway"]["self_employment"]["current"] == 1
    )
    gone = Placement.objects.filter(enrollment=other).first()
    assert c.get(f"{PL}/{gone.pk}").status_code == 404


def test_wage_needs_an_employer_and_it_must_exist(officer, youth, enrollment):
    c = client_for(officer)
    r = c.post(
        PL, {"participant_id": str(youth.pk), "pathway": "wage",
             "start_date": "2026-03-01"}, content_type=JSON,
    )  # fmt: skip
    assert r.status_code == 409
    import uuid

    r = place(c, youth, employer_id=str(uuid.uuid4()))
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "unknown_employer"
    e = Employer.objects.create(name="Acme Traders")
    assert place(c, youth, employer_id=str(e.pk), employer_name_source="").status_code == 201


def test_an_enrollment_that_is_not_the_youths_is_refused(officer, youth, enrollment):
    import uuid

    r = place(client_for(officer), youth, enrollment_id=str(uuid.uuid4()))
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "bad_enrollment"
