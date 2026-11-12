"""Participant directory API (T-058, T-043 core). Synthetic data only."""

import pytest
from django.test import Client

from apps.audit.models import AuditEvent
from apps.configuration.models import (
    Cohort,
    CohortCourse,
    County,
    Course,
    Programme,
    TrainingInstitution,
)
from apps.identity import services as identity
from apps.participants.models import Participant, ParticipantContact, ParticipantEnrollment

URL = "/api/v1/participants"


@pytest.fixture
def world(db):
    inst = TrainingInstitution.objects.create(
        code="I1", name="College", county=County.objects.get(code="01")
    )
    out = {}
    for n in ("1", "2"):
        prog = Programme.objects.create(code=f"P{n}", name=f"Programme {n}")
        course = Course.objects.create(programme=prog, code=f"C{n}", name=f"Course {n}")
        cohort = Cohort.objects.create(
            programme=prog, institution=inst, code=f"K{n}", name=f"Cohort {n}",
            intake_year=2025, batch_no=int(n), phase="1",
        )  # fmt: skip
        cc = CohortCourse.objects.create(cohort=cohort, course=course)
        p = Participant.objects.create(full_name_source=f"Person {n}", gender="female")
        ParticipantEnrollment.objects.create(
            participant=p, cohort_course=cc, programme=prog, institution=inst,
            source_enrollment_no=f"E{n}",
        )  # fmt: skip
        ParticipantContact.objects.create(
            participant=p, kind="phone", value="0700000000", is_primary=True
        )
        out[n] = (p, cohort)
    return out


def client_for(user):
    c = Client()
    c.force_login(user)
    return c


def test_directory_lists_and_filters(world, make_user):
    c = client_for(make_user("steward", "Data steward"))
    body = c.get(URL).json()
    assert body["total"] == 2
    assert c.get(URL, {"q": "Person 2"}).json()["total"] == 1
    assert c.get(URL, {"cohort": str(world["1"][1].pk)}).json()["total"] == 1
    assert c.get(URL, {"q": "E2"}).json()["results"][0]["name"] == "Person 2"
    assert c.get(URL, {"cohort": "not-a-uuid"}).status_code == 400


def test_scope_limits_directory_and_detail(world, make_user):
    u = make_user("officer", "Placement officer")
    identity.set_scopes(actor=None, user=u, scopes=[("cohort", str(world["1"][1].pk))])
    c = client_for(u)
    assert [r["name"] for r in c.get(URL).json()["results"]] == ["Person 1"]
    assert c.get(f"{URL}/{world['1'][0].pk}").status_code == 200
    assert c.get(f"{URL}/{world['2'][0].pk}").status_code == 404


def test_detail_includes_enrollments_and_contacts(world, make_user):
    c = client_for(make_user("steward", "Data steward"))
    d = c.get(f"{URL}/{world['1'][0].pk}").json()
    assert d["enrollments"][0]["enrollment_no"] == "E1"
    assert d["contacts"][0]["value"] == "0700000000"


def test_contacts_hidden_without_permission(world, make_user):
    from django.contrib.auth.models import User

    role = identity.create_role(
        actor=None, name="Viewer only", permissions=["participants.view"], scope_mode="all"
    )
    u = User.objects.create_user("viewer", "v@example.org", "a-long-test-password")
    identity.assign_role(actor=None, user=u, role=role)
    d = client_for(u).get(f"{URL}/{world['1'][0].pk}").json()
    assert "contacts" not in d


def test_edit_is_audited_and_needs_permission(world, make_user):
    p = world["1"][0]
    c = client_for(make_user("steward", "Data steward"))
    r = c.patch(f"{URL}/{p.pk}", {"status": "completed"}, content_type="application/json")
    assert r.status_code == 200 and r.json()["status"] == "completed"
    ev = AuditEvent.objects.get(action="participant.edited")
    assert ev.before == {"status": "unknown"} and ev.after == {"status": "completed"}
    r = c.patch(f"{URL}/{p.pk}", {"status": "bogus"}, content_type="application/json")
    assert r.status_code == 400


def test_filter_options(world, make_user):
    d = client_for(make_user("steward", "Data steward")).get(f"{URL}/filters").json()
    assert len(d["programmes"]) == 2 and len(d["cohorts"]) == 2 and d["counties"]


def test_add_youth_creates_enrollment_contact_and_audit(world, make_user):
    c = client_for(make_user("steward", "Data steward"))
    cc = CohortCourse.objects.filter(cohort=world["1"][1]).first()
    county = County.objects.get(code="02")
    r = c.post(
        URL,
        {
            "full_name_source": "Amina Test",
            "gender": "female",
            "status": "active",
            "age_at_source": 21,
            "origin_county_id": str(county.pk),
            "cohort_course_id": str(cc.pk),
            "enrollment_no": "NEW-1",
            "phone": "0711000000",
        },
        content_type="application/json",
    )
    assert r.status_code == 201, r.content
    p = Participant.objects.get(full_name_source="Amina Test")
    assert p.enrollments.get().programme_id == cc.cohort.programme_id
    assert p.contacts.get().value == "0711000000"
    event = AuditEvent.objects.filter(action="participant.created", object_id=str(p.pk)).get()
    assert "0711000000" not in str(event.after)
    assert event.after["contact_kinds"] == ["phone"]
    # same enrollment number in the same programme is refused
    r = c.post(
        URL,
        {"full_name_source": "Other", "cohort_course_id": str(cc.pk), "enrollment_no": "NEW-1"},
        content_type="application/json",
    )
    assert r.status_code == 400


def test_add_youth_needs_edit_and_a_name(world, make_user):
    viewer = client_for(make_user("viewer", "Assessor"))
    assert (
        viewer.post(URL, {"full_name_source": "X Y"}, content_type="application/json").status_code
        == 403
    )
    c = client_for(make_user("steward", "Data steward"))
    assert c.post(URL, {"gender": "male"}, content_type="application/json").status_code == 400


def test_check_name_finds_existing(world, make_user):
    c = client_for(make_user("steward", "Data steward"))
    found = c.get(f"{URL}/check-name", {"name": "person 1"}).json()["matches"]
    assert [m["name"] for m in found] == ["Person 1"]
    assert c.get(f"{URL}/check-name", {"name": "Nobody Here"}).json()["matches"] == []
