"""Follow-up scheduling (T-066, FR-25/FR-26, BR-10). Synthetic data only.

Acceptance: tasks are generated from the schedule when a placement is confirmed; changing the
schedule affects new placements only and never moves a task that exists; an attempt, a response
with its evidence and a next action are recorded; early follow-ups are counted apart."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.identity import services as identity
from apps.participants.models import Participant
from apps.placements.models import FollowUp, FollowUpStep, Placement

from .test_participants import enrol, world  # noqa: F401

JSON = "application/json"
FU = "/api/v1/followups"
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


def today():
    return timezone.localdate()


def place(c, youth, start=None, **kw):
    body = {
        "participant_id": str(youth.pk), "pathway": "wage", "employer_name_source": "Acme",
        "start_date": (start or today()).isoformat(), **kw,
    }  # fmt: skip
    r = c.post(PL, body, content_type=JSON)
    assert r.status_code == 201, r.content
    return r.json()["id"]


def first_open(c, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return c.get(f"{FU}?{q}").json()["results"][0]


def test_the_default_schedule_is_early_then_tracer_up_to_24_months(db):
    steps = list(FollowUpStep.objects.filter(active=True))
    assert [s.offset_days for s in steps] == [30, 90, 183, 365, 730]
    assert [s.kind for s in steps] == ["early", "early", "tracer", "tracer", "tracer"]


def test_a_placement_generates_a_task_for_each_step_with_the_due_date(officer, youth, enrollment):
    c = client_for(officer)
    pid = place(c, youth)
    rows = c.get(f"{FU}?placement={pid}").json()["results"]
    assert [r["label"] for r in rows] == [
        "30 days",
        "90 days",
        "6 months",
        "12 months",
        "24 months",
    ]
    assert rows[0]["due_date"] == (today() + timedelta(days=30)).isoformat()
    assert rows[0]["kind"] == "early" and rows[2]["kind"] == "tracer"
    assert all(r["assigned_to_id"] == officer.pk for r in rows)
    assert AuditEvent.objects.filter(action="followup.created").count() == 5


def test_steps_long_overdue_when_generated_are_skipped(officer, youth, enrollment):
    c = client_for(officer)
    pid = place(c, youth, start=today() - timedelta(days=100))  # 30-day step was due 70 days ago
    labels = [r["label"] for r in c.get(f"{FU}?placement={pid}").json()["results"]]
    assert "30 days" not in labels and "90 days" in labels  # 90-day step is 10 days away


def test_generating_twice_never_doubles_the_work(officer, youth, enrollment):
    c = client_for(officer)
    pid = place(c, youth)
    assert (
        c.post(f"{PL}/{pid}/verify", {"source": "phone_call"}, content_type=JSON).status_code == 200
    )
    assert FollowUp.objects.filter(placement_id=pid).count() == 5


def test_an_ended_or_unmapped_episode_makes_no_tasks(officer, youth, enrollment):
    c = client_for(officer)
    pid = place(c, youth)
    Placement.objects.filter(pk=pid).update(end_date=today())
    from apps.placements import services as placements

    p = placements.get(pid)
    assert placements.generate_followups(p, actor=officer) == []
    declined = Placement.objects.create(enrollment=p.enrollment, source_status="Rejected")
    assert placements.generate_followups(declined, actor=officer) == []


def test_changing_the_schedule_affects_new_placements_only(
    officer,
    youth,
    enrollment,
    make_user,
    world,  # noqa: F811
):
    admin = make_user("admin", "Administrator")
    c = client_for(officer)
    pid = place(c, youth)
    before = list(FollowUp.objects.filter(placement_id=pid).values_list("label", "due_date"))
    step = FollowUpStep.objects.get(offset_days=30)
    ac = client_for(admin)
    r = ac.patch(
        f"{FU}/steps/{step.pk}", {"label": "2 weeks", "offset_days": 14}, content_type=JSON
    )
    assert r.status_code == 200, r.content
    ac.post(
        f"{FU}/steps",
        {"kind": "tracer", "label": "18 months", "offset_days": 548},
        content_type=JSON,
    )
    assert (
        list(FollowUp.objects.filter(placement_id=pid).values_list("label", "due_date")) == before
    )
    # a placement confirmed afterwards uses the new schedule
    second = Participant.objects.create(full_name_source="Test Youth C", assigned_officer=officer)
    enrol(world, second)
    pid2 = place(c, second)
    labels = [r["label"] for r in c.get(f"{FU}?placement={pid2}").json()["results"]]
    assert "2 weeks" in labels and "18 months" in labels and "30 days" not in labels


def test_only_config_managers_change_the_schedule_and_the_rules_hold(officer, make_user):
    admin = make_user("admin", "Administrator")
    body = {"kind": "tracer", "label": "5 months", "offset_days": 150}
    assert client_for(officer).post(f"{FU}/steps", body, content_type=JSON).status_code == 403
    ac = client_for(admin)
    assert (
        ac.post(f"{FU}/steps", {**body, "offset_days": 733}, content_type=JSON).status_code == 400
    )
    clash = ac.post(f"{FU}/steps", {**body, "offset_days": 30}, content_type=JSON)
    assert clash.status_code == 409 and clash.json()["errors"][0]["code"] == "duplicate_offset"
    assert ac.post(f"{FU}/steps", body, content_type=JSON).status_code == 201
    off = ac.get(f"{FU}/steps").json()["results"]
    assert len(off) == 6


def test_an_attempt_is_recorded_and_sets_the_next_action(officer, youth, enrollment):
    c = client_for(officer)
    place(c, youth)
    row = first_open(c)
    nxt = (today() + timedelta(days=2)).isoformat()
    r = c.post(
        f"{FU}/{row['id']}/attempts",
        {"method": "phone", "reached": False, "note": "No answer", "next_action": "Call again",
         "next_action_date": nxt}, content_type=JSON,
    )  # fmt: skip
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["next_action"] == "Call again" and d["next_action_date"] == nxt
    assert len(d["attempt_list"]) == 1 and d["attempt_list"][0]["reached"] is False
    assert d["status"] == "open"
    ev = AuditEvent.objects.get(action="followup.attempted")
    assert "No answer" not in str(ev.after)  # the typed text stays out of the audit trail


def test_an_attempt_needs_a_method_a_note_when_not_reached_and_no_future_date(
    officer, youth, enrollment
):
    c = client_for(officer)
    place(c, youth)
    pk = first_open(c)["id"]
    url = f"{FU}/{pk}/attempts"
    assert c.post(url, {"method": "pigeon", "reached": True}, content_type=JSON).status_code == 400
    r = c.post(url, {"method": "phone", "reached": False}, content_type=JSON)
    assert r.status_code == 409 and r.json()["errors"][0]["field"] == "note"
    future = (today() + timedelta(days=1)).isoformat()
    r = c.post(url, {"method": "phone", "reached": True, "made_on": future}, content_type=JSON)
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "future"


def test_completing_needs_a_response_and_evidence_and_then_closes(officer, youth, enrollment):
    c = client_for(officer)
    place(c, youth)
    pk = first_open(c)["id"]
    url = f"{FU}/{pk}/complete"
    assert c.post(url, {"still_employed": True}, content_type=JSON).status_code == 400
    r = c.post(url, {"still_employed": True, "evidence_source": "phone_call", "note": "Happy"},
               content_type=JSON)  # fmt: skip
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["status"] == "done" and d["still_employed"] is True
    assert d["evidence_source_label"] == "Phone call with the youth or employer"
    assert d["closed_by"] and not d["can"]["work"]
    again = c.post(f"{FU}/{pk}/attempts", {"method": "phone", "reached": True}, content_type=JSON)
    assert again.status_code == 409 and again.json()["errors"][0]["code"] == "not_open"


def test_unreachable_needs_an_attempt_and_cancel_needs_a_reason(officer, youth, enrollment):
    c = client_for(officer)
    place(c, youth)
    pk = first_open(c)["id"]
    r = c.post(f"{FU}/{pk}/unreachable", {}, content_type=JSON)
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "no_attempts"
    c.post(f"{FU}/{pk}/attempts", {"method": "sms", "reached": False, "note": "No reply"},
           content_type=JSON)  # fmt: skip
    ok = c.post(f"{FU}/{pk}/unreachable", {"note": "Phone off"}, content_type=JSON)
    assert ok.status_code == 200 and ok.json()["status"] == "unreachable"
    other = [r for r in c.get(f"{FU}").json()["results"]][0]["id"]
    assert c.post(f"{FU}/{other}/cancel", {"reason": ""}, content_type=JSON).status_code == 400
    done = c.post(f"{FU}/{other}/cancel", {"reason": "Youth emigrated"}, content_type=JSON)
    assert done.status_code == 200 and done.json()["status"] == "cancelled"
    assert FollowUp.objects.filter(pk=other).exists()  # cancelled, never deleted


def test_a_follow_up_is_never_deleted_and_attempts_are_append_only(officer, youth, enrollment):
    c = client_for(officer)
    place(c, youth)
    f = FollowUp.objects.first()
    with pytest.raises(ValueError):
        f.delete()
    client_for(officer).post(
        f"{FU}/{f.pk}/attempts", {"method": "visit", "reached": True}, content_type=JSON
    )
    a = f.attempts.get()
    a.note = "changed"
    with pytest.raises(ValueError):
        a.save()
    with pytest.raises(ValueError):
        a.delete()


def test_only_the_manager_reassigns_and_the_new_owner_must_work_cases(
    officer, manager, make_user, youth, enrollment
):
    c = client_for(officer)
    place(c, youth)
    pk = first_open(c)["id"]
    body = {"owner_id": officer.pk}
    assert c.post(f"{FU}/{pk}/assign", body, content_type=JSON).status_code == 403
    mc = client_for(manager)
    viewer = make_user("plain", "Manager")  # a manager cannot work cases
    bad = mc.post(f"{FU}/{pk}/assign", {"owner_id": viewer.pk}, content_type=JSON)
    assert bad.status_code == 409 and bad.json()["errors"][0]["code"] == "bad_user"
    other = make_user("otherofficer", "Placement officer")
    ok = mc.post(f"{FU}/{pk}/assign", {"owner_id": other.pk}, content_type=JSON)
    assert ok.status_code == 200 and ok.json()["assigned_to_id"] == other.pk
    assert mc.get(f"{FU}/{pk}").json()["can"]["assign"]
    assert not mc.get(f"{FU}/{pk}").json()["can"]["work"]  # a manager reads, does not work


def test_scope_filters_state_and_counts_reconcile(officer, youth, stranger, enrollment, world):  # noqa: F811
    c = client_for(officer)
    pid = place(c, youth, start=today() - timedelta(days=40))  # the 30-day step is 10 days late
    other = enrol(world, stranger)  # outside this officer's scope
    Placement.objects.create(
        enrollment=other, source_status="Employment", status="placed", pathway="wage",
        start_date=today(),
    )  # fmt: skip
    from apps.placements import services as placements

    placements.generate_followups(Placement.objects.get(enrollment=other), actor=officer)
    rows = c.get(f"{FU}?state=all").json()
    assert rows["total"] == 5  # only the officer's own youth
    overdue = c.get(f"{FU}?state=overdue").json()
    assert overdue["total"] == 1 and overdue["results"][0]["overdue"] is True
    assert c.get(f"{FU}?kind=tracer").json()["total"] == 3
    assert c.get(f"{FU}?q=Test Youth A").json()["total"] == 5
    assert c.get(f"{FU}?q=Nobody").json()["total"] == 0
    s = c.get(f"{FU}/summary").json()
    assert s["open"] == 5 and s["overdue"] == 1 and s["by_kind"]["early"]["open"] == 2
    gone = FollowUp.objects.filter(placement__enrollment=other).first()
    assert c.get(f"{FU}/{gone.pk}").status_code == 404
    assert c.post(f"{FU}/{gone.pk}/cancel", {"reason": "x"}, content_type=JSON).status_code == 404
    assert pid  # placement id kept for readability


def test_early_follow_ups_due_and_done_are_counted_apart(officer, youth, enrollment):
    c = client_for(officer)
    place(c, youth)
    early = first_open(c, kind="early")
    c.post(f"{FU}/{early['id']}/complete",
           {"still_employed": True, "evidence_source": "document"}, content_type=JSON)  # fmt: skip
    s = c.get(f"{FU}/summary").json()["by_kind"]
    assert s["early"] == {"label": "Early follow-up", "open": 1, "done": 1}
    assert s["tracer"]["open"] == 3 and s["tracer"]["done"] == 0


def test_the_queue_lists_follow_ups_and_counts_them(officer, manager, youth, enrollment):
    c = client_for(officer)
    place(c, youth, start=today() - timedelta(days=40))
    q = c.get("/api/v1/cases/queue").json()
    assert q["counts"]["followups_open"] == 5 and q["counts"]["followups_overdue"] == 1
    assert q["followups"][0]["overdue"] is True  # soonest due, so overdue first
    assert (
        client_for(manager).get("/api/v1/cases/queue?mine=1").json()["counts"]["followups_open"]
        == 0
    )
    assert (
        client_for(manager).get("/api/v1/cases/queue?mine=0").json()["counts"]["followups_open"]
        == 5
    )


def test_history_records_every_change(officer, youth, enrollment):
    c = client_for(officer)
    place(c, youth)
    pk = first_open(c)["id"]
    c.post(f"{FU}/{pk}/attempts", {"method": "phone", "reached": True}, content_type=JSON)
    c.post(f"{FU}/{pk}/complete", {"still_employed": False, "evidence_source": "phone_call"},
           content_type=JSON)  # fmt: skip
    actions = [e["action"] for e in c.get(f"{FU}/{pk}/history").json()]
    assert {"followup.created", "followup.attempted", "followup.completed"} <= set(actions)
