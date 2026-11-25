"""Disability in the equity report (NEW-043, D-082): only with the flag on and the permission,
small groups hidden, "Not recorded" as its own group, no value in the audit trail. Synthetic."""

import pytest
from django.core.cache import cache
from django.test import Client

from apps.audit.models import AuditEvent
from apps.configuration.models import FeatureFlag
from apps.identity.models import Role
from apps.participants.models import Participant
from apps.reporting.reports import SUPPRESSED, suppress_small

pytestmark = pytest.mark.django_db
URL = "/api/v1/reporting/reports/equity-and-reach"


@pytest.fixture(autouse=True)
def _fresh():
    cache.clear()


def client(user):
    c = Client()
    c.force_login(user)
    return c


def people(yes, no, unrecorded):
    for n, value in ((yes, "yes"), (no, "no"), (unrecorded, "not_recorded")):
        for _ in range(n):
            Participant.objects.create(full_name_source="Synthetic Person", disability=value)


@pytest.fixture
def reader(make_user):
    role = Role.objects.get(name="Administrator")
    role.permissions = [*role.permissions, "participants.view_disability"]
    role.save()
    return make_user("reader", "Administrator")


def table(user):
    body = client(user).get(URL).json()
    return next((t for t in body["tables"] if t["id"] == "disability"), None), body


def test_no_breakdown_while_the_flag_is_off(reader):
    people(6, 6, 6)
    found, body = table(reader)
    assert found is None
    assert any("not shown" in n for n in body["notes"])


def test_no_breakdown_without_the_permission(make_user):
    FeatureFlag.objects.create(key="participants.disability", enabled=True)
    people(6, 6, 6)
    found, _ = table(make_user("plain", "Administrator"))
    assert found is None


def test_breakdown_shows_three_groups_with_not_recorded_apart(reader):
    FeatureFlag.objects.create(key="participants.disability", enabled=True)
    people(6, 7, 8)
    found, _ = table(reader)
    rows = {r[0]: r for r in found["rows"]}
    assert rows["Yes"][1] == 6 and rows["No"][1] == 7 and rows["Not recorded"][1] == 8


def test_a_small_group_is_hidden_and_so_is_the_next_smallest(reader):
    FeatureFlag.objects.create(key="participants.disability", enabled=True)
    people(2, 9, 5)  # the limit is 5: only "Yes" is under it
    found, _ = table(reader)
    rows = {r[0]: r for r in found["rows"]}
    assert rows["Yes"][1] == SUPPRESSED
    assert rows["Not recorded"][1] == SUPPRESSED  # else Yes = total - No - Not recorded
    assert rows["No"][1] == 9


def test_suppress_small_leaves_big_groups_alone():
    rows = [["A", 10, 5, 2, 20], ["B", 8, 1, 1, 12]]
    assert suppress_small(rows, 5) == rows


def test_each_report_is_logged_without_any_answer(reader):
    FeatureFlag.objects.create(key="participants.disability", enabled=True)
    people(6, 6, 6)
    table(reader)
    ev = AuditEvent.objects.get(action="participant.disability_reported")
    assert ev.after in (None, {}) and ev.before in (None, {})


def test_the_dashboard_stops_listing_disability_as_a_gap_once_on(reader):
    url = "/api/v1/reporting/dashboard"
    before = client(reader).get(url).json()["not_captured"]
    assert any(line.startswith("Disability") for line in before)
    FeatureFlag.objects.create(key="participants.disability", enabled=True)
    cache.clear()
    after = client(reader).get(url).json()["not_captured"]
    assert not any(line.startswith("Disability") for line in after)
