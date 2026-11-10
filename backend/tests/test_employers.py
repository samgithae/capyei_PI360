"""Employer management (T-044, FR-11). Synthetic data only."""

import pytest
from django.test import Client

from apps.audit.models import AuditEvent
from apps.configuration.models import County, Sector
from apps.employers.models import Employer

URL = "/api/v1/employers"
JSON = "application/json"


@pytest.fixture
def steward(make_user):
    c = Client()
    c.force_login(make_user("steward", "Data steward"))
    return c


def post(c, **body):
    return c.post(URL, body, content_type=JSON)


def test_create_validates_and_audits(steward, db):
    sector = Sector.objects.create(code="S1", name="Retail")
    r = post(steward, name="  Acme Traders  ", sector_id=str(sector.pk),
             county_id=str(County.objects.get(code="01").pk))  # fmt: skip
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Acme Traders" and body["sector"] == "Retail" and body["county"]
    assert AuditEvent.objects.filter(action="employer.created", object_id=body["id"]).exists()
    assert post(steward, name="   ").status_code == 400
    assert post(steward, name="X", status="bogus").status_code == 400


def test_duplicate_name_warns_then_allows_confirmation(steward, db):
    post(steward, name="Acme Traders Ltd")
    r = post(steward, name="ACME traders, ltd.")
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "duplicate_name" and r.json()["matches"]
    assert Employer.objects.count() == 1
    assert post(steward, name="ACME traders, ltd.", confirm_duplicate=True).status_code == 201
    assert post(steward, name="Completely Different").status_code == 201
    chk = steward.get(f"{URL}/check-name", {"name": "acme traders ltd"}).json()
    assert len(chk["matches"]) == 2


def test_update_history_and_rename_duplicate_check(steward, db):
    a = post(steward, name="Alpha Works").json()
    post(steward, name="Beta Works")
    r = steward.patch(
        f"{URL}/{a['id']}", {"status": "inactive", "notes": "closed"}, content_type=JSON
    )
    assert r.status_code == 200 and r.json()["status"] == "inactive"
    r = steward.patch(f"{URL}/{a['id']}", {"name": "Beta  Works"}, content_type=JSON)
    assert r.status_code == 409
    h = steward.get(f"{URL}/{a['id']}/history").json()
    assert [e["action"] for e in h] == ["employer.updated", "employer.created"]
    assert h[0]["before"]["status"] == "active" and h[0]["after"]["status"] == "inactive"
    # an unchanged save writes no event
    steward.patch(f"{URL}/{a['id']}", {"status": "inactive"}, content_type=JSON)
    assert len(steward.get(f"{URL}/{a['id']}/history").json()) == 2


def test_contacts_one_primary_and_removal(steward, db):
    e = post(steward, name="Gamma Ltd").json()
    base = f"{URL}/{e['id']}/contacts"
    c1 = steward.post(base, {"name": "Ann", "is_primary": True}, content_type=JSON).json()
    c2 = steward.post(base, {"name": "Bob", "is_primary": True}, content_type=JSON).json()
    contacts = steward.get(f"{URL}/{e['id']}").json()["contacts"]
    assert [c["name"] for c in contacts if c["is_primary"]] == ["Bob"]
    assert (
        steward.post(base, {"name": "Bad", "email": "nope"}, content_type=JSON).status_code == 400
    )
    r = steward.patch(f"{base}/{c1['id']}", {"phone": "0700"}, content_type=JSON)
    assert r.json()["phone"] == "0700"
    assert steward.delete(f"{base}/{c2['id']}").status_code == 204
    assert steward.delete(f"{base}/{c2['id']}").status_code == 404


def test_list_filters(steward, db):
    sector = Sector.objects.create(code="S1", name="Retail")
    post(steward, name="Shop One", sector_id=str(sector.pk))
    post(steward, name="Farm Two")
    assert steward.get(URL).json()["total"] == 2
    assert steward.get(URL, {"q": "shop"}).json()["total"] == 1
    assert steward.get(URL, {"sector": str(sector.pk)}).json()["total"] == 1
    assert steward.get(URL, {"status": "prospect"}).json()["total"] == 0
    assert steward.get(URL, {"sector": "bad"}).status_code == 400
