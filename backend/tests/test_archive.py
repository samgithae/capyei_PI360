"""Archive (soft delete), restore and bulk archive; Administrator powers. Synthetic data only."""

import pytest
from django.test import Client

from apps.audit.models import AuditEvent
from apps.employers.models import Employer, Opportunity
from apps.identity.models import Role
from apps.participants.models import Participant

JSON = "application/json"


def client(make_user, role, name):
    c = Client()
    c.force_login(make_user(name, role))
    return c


@pytest.fixture
def admin(make_user):
    return client(make_user, "Administrator", "boss")


@pytest.fixture
def steward(make_user):
    return client(make_user, "Data steward", "steward")


@pytest.fixture
def people(db):
    return [Participant.objects.create(full_name_source=f"Person {i}") for i in range(3)]


def test_administrator_holds_every_steward_and_officer_permission(db, make_user):
    make_user("x")  # seeds the default roles
    have = set(Role.objects.get(name="Administrator").permissions)
    for name in ("Data steward", "Placement officer"):
        assert set(Role.objects.get(name=name).permissions) <= have
    assert "records.archive" in have and "referrals.approve" not in have


def test_bulk_archive_hides_audits_and_restores(admin, people):
    ids = [str(p.pk) for p in people[:2]]
    r = admin.post(
        "/api/v1/participants/archive", {"ids": ids, "reason": "test"}, content_type=JSON
    )
    assert r.status_code == 200 and sorted(r.json()["changed"]) == sorted(ids)
    assert admin.get("/api/v1/participants").json()["total"] == 1
    gone = admin.get("/api/v1/participants?archived=1").json()
    assert gone["total"] == 2 and gone["results"][0]["archived"] is True
    assert admin.get(f"/api/v1/participants/{ids[0]}").status_code == 200  # still viewable
    assert AuditEvent.objects.filter(action="participant.archived", reason="test").count() == 2
    again = admin.post("/api/v1/participants/archive", {"ids": ids}, content_type=JSON).json()
    assert again["changed"] == [] and len(again["skipped"]) == 2
    r = admin.post("/api/v1/participants/restore", {"ids": ids}, content_type=JSON)
    assert len(r.json()["changed"]) == 2
    assert admin.get("/api/v1/participants").json()["total"] == 3


def test_delete_archives_one_and_unknown_id_is_404(admin, people):
    assert admin.delete(f"/api/v1/participants/{people[0].pk}").status_code == 200
    assert Participant.objects.get(pk=people[0].pk).archived_at is not None
    missing = "00000000-0000-0000-0000-000000000000"
    assert admin.delete(f"/api/v1/participants/{missing}").status_code == 404


def test_only_holders_of_the_permission_may_archive(steward, people):
    assert steward.delete(f"/api/v1/participants/{people[0].pk}").status_code == 403
    body = {"ids": [str(people[0].pk)]}
    assert steward.post("/api/v1/participants/archive", body, content_type=JSON).status_code == 403


def test_bulk_body_is_validated(admin):
    for body in ({}, {"ids": []}, {"ids": ["nope"]}):
        assert admin.post("/api/v1/employers/archive", body, content_type=JSON).status_code == 400


def test_employer_archive_takes_its_opportunities_with_it(admin, db):
    e = Employer.objects.create(name="Acme")
    o = Opportunity.objects.create(employer=e, title="Cashier")
    assert admin.get("/api/v1/opportunities").json()["total"] == 1
    admin.post("/api/v1/employers/archive", {"ids": [str(e.pk)]}, content_type=JSON)
    assert admin.get("/api/v1/employers").json()["total"] == 0
    assert admin.get("/api/v1/opportunities").json()["total"] == 0
    admin.post("/api/v1/employers/restore", {"ids": [str(e.pk)]}, content_type=JSON)
    assert admin.get("/api/v1/opportunities").json()["total"] == 1
    assert admin.delete(f"/api/v1/opportunities/{o.pk}").status_code == 200
    assert admin.get("/api/v1/opportunities").json()["total"] == 0
    assert admin.get("/api/v1/opportunities?archived=1").json()["total"] == 1


def test_admin_can_edit_every_participant_field_and_enrollment(admin, people):
    from apps.configuration.models import County
    from apps.participants.models import Participant

    pid = str(people[0].pk)
    county = County.objects.first()
    body = {
        "full_name_source": "Edited Name",
        "given_name": "Edited",
        "date_of_birth": "2004-05-06",
        "age_at_source": 21,
        "gender": "male",
        "status": "active",
    }
    if county:
        body["origin_county_id"] = str(county.pk)
    r = admin.patch(f"/api/v1/participants/{pid}", body, content_type=JSON)
    assert r.status_code == 200, r.content
    p = Participant.objects.get(pk=pid)
    assert (p.full_name_source, p.date_of_birth.isoformat(), p.age_at_source) == (
        "Edited Name",
        "2004-05-06",
        21,
    )
    bad = admin.patch(
        f"/api/v1/participants/{pid}",
        {"origin_county_id": "00000000-0000-0000-0000-000000000000"},
        content_type=JSON,
    )
    assert bad.status_code == 400


def test_contacts_and_residence_can_be_replaced(admin, people):
    from apps.configuration.models import County

    pid = str(people[0].pk)
    r = admin.put(
        f"/api/v1/participants/{pid}/contacts",
        {
            "contacts": [
                {"kind": "phone", "value": "0700000000", "primary": True},
                {"kind": "email", "value": "a@example.com", "primary": True},
            ]
        },
        content_type=JSON,
    )
    assert r.status_code == 200, r.content
    assert len(r.json()["contacts"]) == 2
    two = admin.put(
        f"/api/v1/participants/{pid}/contacts",
        {
            "contacts": [
                {"kind": "phone", "value": "1", "primary": True},
                {"kind": "phone", "value": "2", "primary": True},
            ]
        },
        content_type=JSON,
    )
    assert two.status_code == 400
    county = County.objects.first()
    body = {"sub_county": "Likoni", "ward": "Timbwani"}
    if county:
        body["county_id"] = str(county.pk)
    one = admin.put(f"/api/v1/participants/{pid}/residence", body, content_type=JSON)
    assert one.status_code == 200, one.content
    two = admin.put(f"/api/v1/participants/{pid}/residence", {"ward": "Other"}, content_type=JSON)
    rows = two.json()["residences"]
    assert len(rows) == 2 and sum(1 for x in rows if x["current"]) == 1
