"""Staff verification workflow on a youth's profile entries, and the per-youth activity feed.
Synthetic data."""

import pytest
from django.test import Client

from apps.audit import services as audit
from apps.configuration.models import Skill
from apps.identity import services as identity
from apps.identity.models import Role
from apps.participants.models import Participant, ProfileVerification


def api(user=None):
    c = Client()
    if user is not None:
        c.force_login(user)
    return c


@pytest.fixture
def world(db, make_user):
    p = Participant.objects.create(full_name_source="Verify Person")
    c = api(make_user("steward", "Data steward"))
    cook = Skill.objects.get(code="SK-FOOD")
    weld = Skill.objects.get(code="SK-WELDING")
    r = c.put(
        f"/api/v1/participants/{p.pk}/profile",
        {"skills": [{"skill_id": str(cook.pk), "proficiency": 2}]},
        content_type="application/json",
    )
    assert r.status_code == 200, r.json()
    return {
        "p": p,
        "c": c,
        "cook": cook,
        "weld": weld,
        "skill_id": r.json()["skills"][0]["id"],
        "profile": f"/api/v1/participants/{p.pk}/profile",
        "verification": f"/api/v1/participants/{p.pk}/verification",
        "activity": f"/api/v1/participants/{p.pk}/activity",
        "cv": f"/api/v1/participants/{p.pk}/cv",
    }


def decide(w, **body):
    base = {"kind": "skill", "id": w["skill_id"], "status": "verified", "method": "interview"}
    return w["c"].post(w["verification"], {**base, **body}, content_type="application/json")


def skill_row(w):
    return w["c"].get(w["profile"]).json()["skills"][0]


def test_unchecked_entry_has_no_verification_record(world):
    row = skill_row(world)
    assert row["verified"] is False and row["verification"] is None


def test_verified_needs_a_method_and_marks_the_entry_verified(world):
    assert decide(world, method="").status_code == 400
    r = decide(world, notes="Saw the practical test")
    assert r.status_code == 200, r.json()
    row = r.json()["skills"][0]
    assert row["verified"] is True
    assert row["verification"]["status"] == "verified"
    assert row["verification"]["method"] == "interview"
    assert row["verification"]["notes"] == "Saw the practical test"
    assert row["verification"]["decided_by"] == "steward"


def test_rejected_needs_a_reason_and_is_not_verified(world):
    assert decide(world, status="rejected", method="").status_code == 400
    row = decide(world, status="rejected", method="", notes="Referee denied it").json()["skills"][0]
    assert row["verified"] is False and row["verification"]["status"] == "rejected"


def test_pending_clears_an_earlier_verification(world):
    decide(world)
    row = decide(world, status="pending", method="").json()["skills"][0]
    assert row["verified"] is False and row["verification"]["status"] == "pending"


def test_unknown_entry_status_or_method_is_refused(world):
    assert decide(world, id="00000000-0000-0000-0000-000000000000").status_code == 400
    assert decide(world, status="maybe").status_code == 400
    assert decide(world, method="vibes").status_code == 400


def test_changing_a_verified_entry_asks_for_reassessment(world):
    decide(world)
    r = world["c"].put(
        world["profile"],
        {
            "skills": [
                {"id": world["skill_id"], "skill_id": str(world["cook"].pk), "proficiency": 3}
            ]
        },
        content_type="application/json",
    )
    row = r.json()["skills"][0]
    assert row["verified"] is False
    assert row["verification"]["status"] == "needs_reassessment"


def test_saving_an_entry_unchanged_keeps_its_verification(world):
    decide(world)
    world["c"].put(
        world["profile"],
        {
            "skills": [
                {"id": world["skill_id"], "skill_id": str(world["cook"].pk), "proficiency": 2}
            ]
        },
        content_type="application/json",
    )
    row = skill_row(world)
    assert row["verified"] is True and row["verification"]["status"] == "verified"


def test_removing_an_entry_removes_its_verification_record(world):
    decide(world)
    world["c"].put(world["profile"], {"skills": []}, content_type="application/json")
    assert not ProfileVerification.objects.filter(participant=world["p"]).exists()


def test_the_older_verify_endpoint_keeps_the_record_in_step(world):
    r = world["c"].post(
        f"/api/v1/participants/{world['p'].pk}/profile/verify",
        {"kind": "skill", "id": world["skill_id"], "verified": True},
        content_type="application/json",
    )
    assert r.json()["skills"][0]["verification"]["status"] == "verified"


def test_verifying_needs_the_edit_permission_and_scope(world, make_user):
    role = identity.create_role(
        actor=None, name="Read only", permissions=["participants.view_profile"], scope_mode="all"
    )
    reader = make_user("reader")
    identity.assign_role(actor=None, user=reader, role=Role.objects.get(pk=role.pk))
    body = {"kind": "skill", "id": world["skill_id"], "status": "verified", "method": "other"}
    assert (
        api(reader).post(world["verification"], body, content_type="application/json").status_code
        == 403
    )
    out = make_user("outsider", "Placement officer")  # assigned scope, nothing assigned
    assert (
        api(out).post(world["verification"], body, content_type="application/json").status_code
        == 404
    )
    assert api().post(world["verification"], body).status_code in (401, 403)


def test_the_cv_never_carries_verification_detail(world):
    decide(world, notes="PRIVATE-NOTE-XYZ")
    text = world["c"].get(world["cv"]).content.decode()
    assert "PRIVATE-NOTE-XYZ" not in text and "verification" not in text
    assert "needs_reassessment" not in text


def test_the_activity_feed_shows_checks_without_notes_and_hides_email_actors(world, make_user):
    decide(world, notes="PRIVATE-NOTE-XYZ")
    audit.record(
        actor=make_user("kamau@example.test"),
        action="participant.profile_edited",
        object_type="participant",
        object_id=world["p"].pk,
        after={"skills": 1},
    )
    r = world["c"].get(world["activity"])
    assert r.status_code == 200
    text = r.content.decode()
    assert "PRIVATE-NOTE-XYZ" not in text and "kamau@example.test" not in text
    rows = r.json()["results"]
    assert rows[0]["actor"] == "Account holder"
    check = next(x for x in rows if x["action"] == "participant.profile_verification")
    assert check["detail"] == {"kind": "skill", "status": "verified", "method": "interview"}


def test_the_activity_feed_needs_view_profile_and_scope(world, make_user):
    role = identity.create_role(actor=None, name="No profile", permissions=[], scope_mode="all")
    nobody = make_user("nobody")
    identity.assign_role(actor=None, user=nobody, role=Role.objects.get(pk=role.pk))
    assert api(nobody).get(world["activity"]).status_code == 403
    out = make_user("outsider", "Placement officer")
    assert api(out).get(world["activity"]).status_code == 404
    assert api().get(world["activity"]).status_code in (401, 403)
