"""NEW-039 / NEW-076: staff-assisted exit feedback, one per ended placement, confidential comment
by default. Synthetic data only."""

# ruff: noqa: F811  (pytest fixtures imported from other test modules)

import pytest

from apps.audit.models import AuditEvent
from apps.identity import services as identity
from apps.intelligence.models import RuleSetting
from apps.placements.models import ExitFeedback

from .test_casework import JSON, PL, client_for, enrollment, officer, place, youth  # noqa: F401
from .test_participants import world  # noqa: F401

COMMENT = "Supervisor shouted at me every day"


def ended(c, youth):
    pid = place(c, youth).json()["id"]
    c.post(f"{PL}/{pid}/end", {"end_date": "2026-06-01"}, content_type=JSON)
    return pid


def give(c, pid, **kw):
    body = {"rating": 2, "comment": COMMENT, **kw}
    return c.post(f"{PL}/{pid}/exit-feedback", body, content_type=JSON)


@pytest.fixture
def reader(make_user, officer):  # noqa: F811
    role = identity.create_role(
        actor=None, name="Exit reader", scope_mode="all",
        permissions=["placements.view", "placements.view_exit_comments"],
    )  # fmt: skip
    u = make_user("reader")
    identity.assign_role(actor=None, user=u, role=role)
    return u


def test_records_one_and_rejects_a_second(officer, youth, enrollment):  # noqa: F811
    c = client_for(officer)
    pid = ended(c, youth)
    r = give(c, pid)
    assert r.status_code == 201, r.content
    assert give(c, pid, rating=5).status_code == 409
    assert ExitFeedback.objects.count() == 1


def test_needs_an_ended_placement_and_a_valid_rating(officer, youth, enrollment):  # noqa: F811
    c = client_for(officer)
    running = place(c, youth).json()["id"]
    assert give(c, running).status_code == 409
    c.post(f"{PL}/{running}/end", {"end_date": "2026-06-01"}, content_type=JSON)
    assert give(c, running, rating=6).status_code == 400
    assert give(c, running, rating=0).status_code == 400


def test_confidential_by_default_and_hidden_without_the_grant(
    officer,
    youth,
    enrollment,
    reader,  # noqa: F811
):
    c = client_for(officer)
    pid = ended(c, youth)
    body = give(c, pid).json()["exit_feedback"]
    assert body["rating"] == 2 and body["confidential"] and body["comment_hidden"]
    assert COMMENT not in str(body)
    seen = client_for(reader).get(f"{PL}/{pid}").json()["exit_feedback"]
    assert seen["comment"] == COMMENT and not seen["comment_hidden"]


def test_changing_the_default_affects_new_feedback_only(officer, youth, enrollment):  # noqa: F811
    c = client_for(officer)
    first = ended(c, youth)
    give(c, first)
    RuleSetting.objects.create(key="exit.confidential_default", value=0)
    second = place(c, youth, start_date="2026-07-01").json()["id"]
    c.post(f"{PL}/{second}/end", {"end_date": "2026-08-01"}, content_type=JSON)
    give(c, second)
    flags = {str(f.placement_id): f.confidential for f in ExitFeedback.objects.all()}
    assert flags == {first: True, second: False}
    assert COMMENT in str(c.get(f"{PL}/{second}").json()["exit_feedback"])


def test_audit_never_holds_the_comment(officer, youth, enrollment):  # noqa: F811
    c = client_for(officer)
    pid = ended(c, youth)
    give(c, pid)
    ev = AuditEvent.objects.get(action="placement.exit_feedback_recorded", object_id=pid)
    assert COMMENT not in str(ev.after) and ev.after["has_comment"] is True


def test_feedback_cannot_be_edited_or_deleted(officer, youth, enrollment):  # noqa: F811
    c = client_for(officer)
    give(c, ended(c, youth))
    fb = ExitFeedback.objects.get()
    fb.rating = 5
    with pytest.raises(ValueError):
        fb.save()
    with pytest.raises(ValueError):
        fb.delete()
