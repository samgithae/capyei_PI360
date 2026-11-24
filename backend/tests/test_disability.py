# ruff: noqa: F811
"""Disability (NEW-040, NEW-073, D-082): off by default, permission-gated, Yes/No with an optional
description, every access logged and no value ever in the audit trail. Synthetic data only."""

import pytest
from django.core.cache import cache
from django.test import Client

from apps.audit.models import AuditEvent
from apps.configuration.models import FeatureFlag
from apps.identity.models import Role
from apps.participants.models import Participant

from .test_youth_portal import person  # noqa: F401

JSON = "application/json"
NOTE = "Uses a wheelchair"


def api(user=None):
    c = Client(enforce_csrf_checks=False)
    if user:
        c.force_login(user)
    return c


@pytest.fixture(autouse=True)
def _fresh():
    cache.clear()


@pytest.fixture
def flag_on(db):
    FeatureFlag.objects.create(key="participants.disability", enabled=True)


@pytest.fixture
def reader(make_user):
    """A data steward who has also been given the disability permission."""
    role = Role.objects.get(name="Data steward")
    role.permissions = [*role.permissions, "participants.view_disability"]
    role.save()
    return make_user("reader", "Data steward")


def url(p):
    return f"/api/v1/participants/{p.pk}/disability"


def test_the_route_does_not_exist_while_the_flag_is_off(reader, person):
    assert api(reader).get(url(person)).status_code == 404
    assert api(reader).put(url(person), {"disability": "no"}, content_type=JSON).status_code == 404


def test_default_roles_do_not_hold_the_permission(make_user, person, flag_on):
    steward = make_user("steward", "Data steward")
    assert api(steward).get(url(person)).status_code == 403
    r = api(steward).put(url(person), {"disability": "yes"}, content_type=JSON)
    assert r.status_code == 403
    person.refresh_from_db()
    assert person.disability == "not_recorded"


def test_a_new_record_is_not_recorded_and_nothing_is_inferred(reader, person, flag_on):
    doc = api(reader).get(url(person)).json()
    assert doc["disability"] == "not_recorded" and doc["recorded_at"] is None


def test_yes_keeps_the_description_no_and_clearing_wipe_it(reader, person, flag_on):
    body = {"disability": "yes", "description": NOTE}
    r = api(reader).put(url(person), body, content_type=JSON)
    assert r.status_code == 200 and r.json()["description"] == NOTE
    assert r.json()["source"] == "staff" and r.json()["recorded_at"]
    r = api(reader).put(url(person), {"disability": "no", "description": NOTE}, content_type=JSON)
    assert r.json()["description"] == "" and r.json()["disability"] == "no"
    r = api(reader).put(url(person), {"disability": "not_recorded"}, content_type=JSON)
    assert r.json()["recorded_at"] is None and r.json()["source"] == ""


def test_there_is_no_prefer_not_to_say_and_junk_is_refused(reader, person, flag_on):
    for bad in ("prefer_not_to_say", "maybe", ""):
        r = api(reader).put(url(person), {"disability": bad}, content_type=JSON)
        assert r.status_code == 400
    r = api(reader).put(
        url(person), {"disability": "yes", "description": "x" * 301}, content_type=JSON
    )
    assert r.status_code == 400


def test_every_read_and_change_is_logged_without_the_value(reader, person, flag_on):
    api(reader).put(url(person), {"disability": "yes", "description": NOTE}, content_type=JSON)
    api(reader).get(url(person))
    api(reader).get(url(person))
    assert AuditEvent.objects.filter(action="participant.disability_changed").count() == 1
    assert AuditEvent.objects.filter(action="participant.disability_viewed").count() == 2
    for ev in AuditEvent.objects.filter(action__startswith="participant.disability"):
        assert NOTE not in str(ev.before) + str(ev.after) + ev.reason
        assert ev.object_id == str(person.pk) and ev.actor_label == "reader"


def test_a_refused_read_writes_no_access_event(make_user, person, flag_on):
    api(make_user("steward", "Data steward")).get(url(person))
    assert not AuditEvent.objects.filter(action="participant.disability_viewed").exists()


def test_it_never_appears_in_the_detail_or_the_directory(reader, person, flag_on):
    api(reader).put(url(person), {"disability": "yes", "description": NOTE}, content_type=JSON)
    detail = api(reader).get(f"/api/v1/participants/{person.pk}")
    listing = api(reader).get("/api/v1/participants")
    for r in (detail, listing):
        assert r.status_code == 200
        assert NOTE not in r.content.decode() and "disability" not in r.content.decode()


def test_a_youth_outside_the_callers_scope_is_a_404(make_user, person, flag_on):
    role = Role.objects.get(name="Placement officer")
    role.permissions = [*role.permissions, "participants.view_disability"]
    role.save()
    officer = make_user("officer", "Placement officer")  # assigned scope, no scope given
    assert api(officer).get(url(person)).status_code == 404


def test_unchanged_answer_does_not_restamp(reader, person, flag_on):
    first = api(reader).put(url(person), {"disability": "no"}, content_type=JSON).json()
    again = api(reader).put(url(person), {"disability": "no"}, content_type=JSON).json()
    assert first["recorded_at"] == again["recorded_at"]
    assert Participant.objects.get(pk=person.pk).disability == "no"
