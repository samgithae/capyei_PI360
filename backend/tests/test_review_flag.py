# ruff: noqa: F811
"""The participant review flag (NEW-050, D-084): four triggers, cleared by an officer, blocks
nothing. Synthetic data only."""

import datetime

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client

from apps.audit.models import AuditEvent
from apps.configuration.models import FeatureFlag
from apps.participants import services as participants
from apps.participants.models import Participant, ReviewEvent
from apps.portal import services as portal
from apps.portal.models import RegistrationRequest

from .test_corrections import ann, run_import  # noqa: F401
from .test_participants import world  # noqa: F401
from .test_youth_portal import EMAIL, activate, person  # noqa: F401

JSON = "application/json"


def api(user=None):
    c = Client(enforce_csrf_checks=False)
    if user:
        c.force_login(user)
    return c


@pytest.fixture(autouse=True)
def _fresh():
    cache.clear()


@pytest.fixture
def steward(make_user):
    return make_user("steward", "Data steward")


def state(p):
    p.refresh_from_db()
    return p.review_state, p.review_reason


def test_existing_and_new_youth_start_with_no_flag(person):
    assert state(person) == ("none", "")
    assert participants.review_history(person) == []


def test_officer_flag_needs_a_reason_and_is_recorded(steward, person):
    url = f"/api/v1/participants/{person.pk}/review"
    assert api(steward).post(url, {"note": "  "}, content_type=JSON).status_code == 400
    assert state(person)[0] == "none"
    r = api(steward).post(url, {"note": "Name looks misspelt"}, content_type=JSON)
    assert r.status_code == 200
    assert state(person) == ("needs_review", "officer_flag")
    hist = api(steward).get(url).json()["results"]
    assert hist[0]["kind"] == "flagged" and hist[0]["note"] == "Name looks misspelt"
    # the audit trail names the cause but never the free-text note
    ev = AuditEvent.objects.get(action="participant.review_flagged")
    assert "misspelt" not in str(ev.after)


def test_mark_reviewed_clears_it_and_keeps_the_history(steward, person):
    url = f"/api/v1/participants/{person.pk}/review"
    api(steward).post(url, {"note": "Check"}, content_type=JSON)
    r = api(steward).delete(url, {"note": "Checked against the register"}, content_type=JSON)
    assert r.status_code == 200 and r.json()["marked"] == 1
    assert state(person)[0] == "reviewed"
    kinds = [h["kind"] for h in api(steward).get(url).json()["results"]]
    assert kinds == ["reviewed", "flagged"]
    # marking again does nothing and adds no history
    assert api(steward).delete(url, content_type=JSON).json()["marked"] == 0
    assert ReviewEvent.objects.filter(participant=person).count() == 2


def test_flag_blocks_nothing(steward, person):
    participants.flag_for_review(p=person, reason="officer_flag", actor=steward)
    r = api(steward).patch(
        f"/api/v1/participants/{person.pk}", {"status": "active"}, content_type=JSON
    )
    assert r.status_code == 200
    assert api(steward).get(f"/api/v1/participants/{person.pk}").json()["review"]["state"] == (
        "needs_review"
    )


def test_bulk_mark_reviewed_ignores_ids_outside_scope(steward, make_user):
    a = Participant.objects.create(full_name_source="Test One")
    b = Participant.objects.create(full_name_source="Test Two")
    for p in (a, b):
        participants.flag_for_review(p=p, reason="self_edit")
    r = api(steward).post(
        "/api/v1/participants/review/mark",
        {"ids": [str(a.pk), str(b.pk), "00000000-0000-0000-0000-000000000000"]},
        content_type=JSON,
    )
    assert r.status_code == 200 and r.json()["marked"] == 2
    assert state(a)[0] == state(b)[0] == "reviewed"


def test_a_read_only_role_cannot_flag_or_clear(make_user, person):
    viewer = make_user("viewer", "Assessor")
    url = f"/api/v1/participants/{person.pk}/review"
    assert api(viewer).post(url, {"note": "x"}, content_type=JSON).status_code == 403
    assert api(viewer).delete(url, content_type=JSON).status_code == 403


def test_reflagging_keeps_the_first_since_and_the_latest_reason(person):
    participants.flag_for_review(p=person, reason="self_edit")
    person.refresh_from_db()
    first = person.review_since
    participants.flag_for_review(p=person, reason="import_change")
    person.refresh_from_db()
    assert person.review_reason == "import_change" and person.review_since == first
    assert ReviewEvent.objects.filter(participant=person).count() == 2


def test_linking_a_self_registration_flags_the_record(steward, person):
    FeatureFlag.objects.update_or_create(key=portal.REGISTRATION_FLAG, defaults={"enabled": True})
    req = RegistrationRequest.objects.create(
        given_name="Test", family_name="Person", date_of_birth=datetime.date(2003, 5, 1),
        email="other.person@example.org", consent_version="draft",
        email_verified_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        status=RegistrationRequest.VERIFIED,
    )  # fmt: skip
    r = api(steward).post(
        f"/api/v1/registrations/{req.pk}/link",
        {"participant_id": str(person.pk), "reason": "Same person"},
        content_type=JSON,
    )
    assert r.status_code == 200, r.content
    assert state(person) == ("needs_review", "self_registration")


def test_a_youth_changing_key_details_flags_the_record_but_contacts_do_not(steward, person):
    activate(person, steward)
    youth = api(User.objects.get(username=EMAIL))
    youth.post("/api/v1/youth/consent", {"version": portal.CONSENT_VERSION}, content_type=JSON)
    only_contact = youth.put(
        "/api/v1/youth/details",
        {"contacts": [{"kind": "email", "value": EMAIL, "primary": True},
                      {"kind": "phone", "value": "+254700000002", "primary": False}]},
        content_type=JSON,
    )  # fmt: skip
    assert only_contact.status_code == 200, only_contact.content
    assert state(person)[0] == "none"
    r = youth.put("/api/v1/youth/details", {"given_name": "Amina"}, content_type=JSON)
    assert r.status_code == 200, r.content
    assert state(person) == ("needs_review", "self_edit")
    # the youth sees none of this
    assert "review" not in youth.get("/api/v1/youth/me").content.decode()


def test_an_import_that_changes_key_fields_flags_it_and_a_no_op_does_not(world, ann):  # noqa: F811
    run_import(world, gender="female", age=20)  # same as on file
    assert state(ann)[0] == "none"
    run_import(world, gender="female", age=25)
    assert state(ann) == ("needs_review", "import_change")


def test_directory_filters_to_the_review_list_and_marks_each_row(steward):
    a = Participant.objects.create(full_name_source="Test Flagged")
    Participant.objects.create(full_name_source="Test Plain")
    participants.flag_for_review(p=a, reason="self_edit")
    everyone = api(steward).get("/api/v1/participants").json()
    assert everyone["total"] == 2
    assert {r["name"]: r["review"] for r in everyone["results"]} == {
        "Test Flagged": "needs_review",
        "Test Plain": "none",
    }
    only = api(steward).get("/api/v1/participants?review=needs_review").json()
    assert [r["name"] for r in only["results"]] == ["Test Flagged"]
    # once reviewed it leaves the list
    api(steward).delete(f"/api/v1/participants/{a.pk}/review", content_type=JSON)
    assert api(steward).get("/api/v1/participants?review=needs_review").json()["total"] == 0
