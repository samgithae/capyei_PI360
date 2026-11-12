"""Admin-editable numbers behind support flags and employer evidence."""

import pytest
from django.test import Client

from apps.audit.models import AuditEvent
from apps.intelligence import services
from apps.intelligence.settings_registry import REGISTRY


def api(user):
    c = Client()
    c.force_login(user)
    return c


URL = "/api/v1/rules/settings"


def put(c, values):
    return c.put(URL, {"values": values}, content_type="application/json")


def test_defaults_apply_until_an_administrator_changes_them(db, make_user):
    assert services.setting("employer.min_referrals") == 5
    c = api(make_user("admin", "Administrator"))
    rows = c.get(URL).json()
    assert {r["key"] for r in rows} == {s.key for s in REGISTRY}
    r = put(c, {"employer.min_referrals": 8})
    assert r.status_code == 200
    assert services.setting("employer.min_referrals") == 8
    assert services.setting("employer.window_days") == 180  # untouched
    assert AuditEvent.objects.filter(action="rule_settings.update").count() == 1
    put(c, {"employer.min_referrals": 8})  # no change, no new audit event
    assert AuditEvent.objects.filter(action="rule_settings.update").count() == 1


@pytest.mark.parametrize(
    "values", [{"nope": 1}, {"employer.min_referrals": 0}, {"employer.min_referrals": "x"},
              {"employer.min_referrals": 2.5}, {"employer.min_referrals": True}]
)  # fmt: skip
def test_bad_values_are_refused_and_nothing_is_saved(db, make_user, values):
    c = api(make_user("admin", "Administrator"))
    assert put(c, {"support.window_days": 30, **values}).status_code == 400
    assert services.setting("support.window_days") == 90


def test_changing_needs_manage_rules(db, make_user):
    assert (
        put(api(make_user("amina", "Placement officer")), {"support.window_days": 30}).status_code
        == 403
    )
    assert Client().get(URL).status_code in (401, 403)
