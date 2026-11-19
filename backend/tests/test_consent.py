"""Privacy notice and consent status (T-054, provisional on D-015).

Consent is a flag on the youth, not a gate: nothing is blocked when it is missing. The whole
feature sits behind the ``consent_tracking`` setting, which is off until an administrator turns it
on."""

import csv
import io
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.configuration import services as configuration
from apps.identity import services as identity
from apps.participants.models import Participant

from .test_participants import world  # noqa: F401

JSON = "application/json"


def client(user):
    c = Client()
    c.force_login(user)
    return c


def switch(on=True):
    configuration.set_flag(actor=None, key="consent_tracking", enabled=on)


@pytest.fixture(autouse=True)
def consent_on(db):
    """Most tests are about the feature, so it starts on; the off tests switch it off."""
    switch(True)


@pytest.fixture
def admin(make_user):
    return make_user("adm", "Administrator")


@pytest.fixture
def ann(world):  # noqa: F811
    return Participant.objects.create(full_name_source="Ann Wanjiru", gender="female")


def put(user, p, body):
    return client(user).put(f"/api/v1/participants/{p.pk}/consent", body, content_type=JSON)


@pytest.mark.django_db
def test_a_youth_starts_with_consent_not_recorded(admin, ann):
    assert ann.consent_status == "not_recorded"
    row = client(admin).get(f"/api/v1/participants/{ann.pk}").json()
    assert row["consent"] == {
        "status": "not_recorded",
        "label": "Not recorded",
        "notice_version": "",
        "recorded_on": None,
    }
    listed = client(admin).get("/api/v1/participants").json()["results"]
    assert listed[0]["consent"] == "not_recorded"


@pytest.mark.django_db
def test_recording_consent_stores_status_version_and_date(admin, ann):
    r = put(admin, ann, {"status": "given", "notice_version": " v1 ", "recorded_on": "2026-11-01"})
    assert r.status_code == 200
    assert r.json()["consent"]["notice_version"] == "v1"
    ann.refresh_from_db()
    assert ann.consent_status == "given"
    assert str(ann.consent_recorded_on) == "2026-11-01"


@pytest.mark.django_db
def test_the_date_defaults_to_today(admin, ann):
    put(admin, ann, {"status": "declined", "notice_version": "v1"})
    ann.refresh_from_db()
    assert ann.consent_recorded_on == timezone.localdate()


@pytest.mark.django_db
def test_a_notice_version_is_required_once_a_decision_is_recorded(admin, ann):
    assert put(admin, ann, {"status": "given"}).status_code == 400
    assert put(admin, ann, {"status": "given", "notice_version": "  "}).status_code == 400
    ann.refresh_from_db()
    assert ann.consent_status == "not_recorded"


@pytest.mark.django_db
def test_the_date_cannot_be_in_the_future(admin, ann):
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    r = put(admin, ann, {"status": "given", "notice_version": "v1", "recorded_on": tomorrow})
    assert r.status_code == 400


@pytest.mark.django_db
def test_clearing_back_to_not_recorded_drops_version_and_date(admin, ann):
    put(admin, ann, {"status": "given", "notice_version": "v1"})
    put(admin, ann, {"status": "not_recorded", "notice_version": "v9"})
    ann.refresh_from_db()
    assert (ann.consent_status, ann.consent_notice_version, ann.consent_recorded_on) == (
        "not_recorded",
        "",
        None,
    )


@pytest.mark.django_db
def test_the_audit_entry_has_status_and_version_but_no_personal_values(admin, ann):
    put(admin, ann, {"status": "given", "notice_version": "v1", "recorded_on": "2026-11-01"})
    e = AuditEvent.objects.get(action="participant.consent_recorded")
    assert e.object_id == str(ann.pk)
    assert e.before["status"] == "not_recorded" and e.after["status"] == "given"
    assert "Ann" not in str(e.before) + str(e.after)


@pytest.mark.django_db
def test_only_people_who_can_edit_a_youth_may_record_consent(make_user, ann):
    viewer = make_user("an", "M&E analyst")
    assert put(viewer, ann, {"status": "given", "notice_version": "v1"}).status_code == 403
    officer = make_user("off", "Placement officer")
    # Officers may edit, but only youth in their own scope: this one is outside it.
    assert put(officer, ann, {"status": "given", "notice_version": "v1"}).status_code == 404


@pytest.mark.django_db
def test_unknown_youth_is_not_found(admin):
    r = client(admin).put(
        "/api/v1/participants/00000000-0000-0000-0000-000000000000/consent",
        {"status": "given", "notice_version": "v1"},
        content_type=JSON,
    )
    assert r.status_code == 404


@pytest.mark.django_db
def test_the_youth_export_offers_and_holds_the_consent_fields(admin, ann):
    identity.grant_permission(
        actor=admin,
        user=admin,
        permission="exports.identifiable",
        purpose="Consent check",
        expires_at=timezone.now() + timedelta(days=3),
    )
    put(admin, ann, {"status": "given", "notice_version": "v1", "recorded_on": "2026-11-01"})
    groups = client(admin).get("/api/v1/exports/fields/youth").json()["groups"]
    keys = {f["key"] for g in groups for f in g["fields"]}
    assert {"consent_status", "consent_notice_version", "consent_recorded_on"} <= keys
    r = client(admin).post(
        "/api/v1/exports/table/youth",
        {
            "format": "csv",
            "purpose": "Consent check",
            "fields": ["name", "consent_status", "consent_notice_version", "consent_recorded_on"],
        },
        content_type=JSON,
    )
    assert r.status_code == 200
    (row,) = csv.DictReader(io.StringIO(r.content.decode().lstrip("﻿")))
    assert row["Consent status"] == "Given"
    assert row["Privacy notice version"] == "v1"
    assert row["Consent recorded on"] == "2026-11-01"


# --- the setting -------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_setting_exists_and_ships_off():
    from django.apps import apps

    flag = apps.get_model("configuration", "FeatureFlag").objects.get(key="consent_tracking")
    assert flag.description and "Off by default" in flag.description
    # The migration seeds it off; the autouse fixture turned it on for these tests.
    switch(False)
    assert configuration.is_enabled("consent_tracking") is False


@pytest.mark.django_db
def test_with_the_setting_off_nothing_about_consent_is_shown(admin, ann):
    switch(False)
    assert "consent" not in client(admin).get(f"/api/v1/participants/{ann.pk}").json()
    assert "consent" not in client(admin).get("/api/v1/participants").json()["results"][0]


@pytest.mark.django_db
def test_with_the_setting_off_consent_cannot_be_recorded(admin, ann):
    switch(False)
    assert put(admin, ann, {"status": "given", "notice_version": "v1"}).status_code == 404
    ann.refresh_from_db()
    assert ann.consent_status == "not_recorded"


@pytest.mark.django_db
def test_with_the_setting_off_exports_do_not_offer_or_hold_consent(admin, ann):
    identity.grant_permission(
        actor=admin,
        user=admin,
        permission="exports.identifiable",
        purpose="Check",
        expires_at=timezone.now() + timedelta(days=3),
    )
    put(admin, ann, {"status": "given", "notice_version": "v1"})
    switch(False)
    groups = client(admin).get("/api/v1/exports/fields/youth").json()["groups"]
    assert "consent" not in {g["key"] for g in groups}
    r = client(admin).post(
        "/api/v1/exports/table/youth",
        {"format": "csv", "purpose": "Check", "fields": ["name", "consent_status"]},
        content_type=JSON,
    )
    header = r.content.decode().lstrip("\ufeff").splitlines()[0]
    assert "Consent" not in header


@pytest.mark.django_db
def test_an_administrator_can_turn_it_on_from_the_settings_api(admin):
    switch(False)
    r = client(admin).patch(
        "/api/v1/config/flags/consent_tracking",
        {"enabled": True, "reason": "Pilot"},
        content_type=JSON,
    )
    assert r.status_code == 200
    assert configuration.is_enabled("consent_tracking") is True
