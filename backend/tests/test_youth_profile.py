"""Capability profile of a youth: qualifications, skills, experience, readiness. Synthetic data."""

import pytest
from django.test import Client

from apps.audit.models import AuditEvent
from apps.configuration.models import QualificationLevel, Sector, Skill
from apps.participants.models import Participant, ParticipantSkill


def api(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def world(db):
    p = Participant.objects.create(full_name_source="Profile Person")
    return {
        "p": p,
        "url": f"/api/v1/participants/{p.pk}/profile",
        "diploma": QualificationLevel.objects.get(code="QL05"),
        "degree": QualificationLevel.objects.get(code="QL07"),
        "cook": Skill.objects.get(code="SK-FOOD"),
        "weld": Skill.objects.get(code="SK-WELDING"),
        "sector": Sector.objects.create(code="S1", name="Hospitality"),
    }


def put(c, w, body):
    return c.put(w["url"], body, content_type="application/json")


def test_empty_profile_reads_as_empty_not_error(world, make_user):
    body = api(make_user("steward", "Data steward")).get(world["url"]).json()
    assert body["qualifications"] == [] and body["skills"] == []
    assert body["summary"] == {"highest_qualification": "", "experience_months": 0, "skills": []}
    assert body["readiness"]["available_from"] is None


def test_write_then_read_summarises_top_level_and_total_months(world, make_user):
    c = api(make_user("steward", "Data steward"))
    r = put(
        c,
        world,
        {
            "qualifications": [
                {"level_id": str(world["diploma"].pk), "title": "Diploma in Food"},
                {"level_id": str(world["degree"].pk), "year_awarded": 2024},
            ],
            "skills": [{"skill_id": str(world["cook"].pk), "proficiency": 3}],
            "experience": [
                {"role_title": "Cook", "months": 10, "sector_id": str(world["sector"].pk)},
                {"role_title": "Waiter", "months": 8},
            ],
            "readiness": {
                "available_from": "2026-12-01",
                "work_patterns": ["full_time", "shift"],
                "interest_sector_ids": [str(world["sector"].pk)],
            },
        },
    )
    assert r.status_code == 200, r.json()
    s = r.json()["summary"]
    assert s["highest_qualification"] == world["degree"].name
    assert s["experience_months"] == 18 and s["skills"] == [world["cook"].name]
    assert r.json()["readiness"]["interest_sectors"] == ["Hospitality"]
    assert AuditEvent.objects.filter(action="participant.profile_edited").exists()


def test_omitted_section_is_left_alone_and_present_section_replaces(world, make_user):
    c = api(make_user("steward", "Data steward"))
    put(c, world, {"skills": [{"skill_id": str(world["cook"].pk)}]})
    put(c, world, {"experience": [{"role_title": "Cook", "months": 3}]})
    body = c.get(world["url"]).json()
    assert len(body["skills"]) == 1 and len(body["experience"]) == 1
    body = put(c, world, {"skills": [{"skill_id": str(world["weld"].pk)}]}).json()
    assert [s["skill"] for s in body["skills"]] == [world["weld"].name]
    assert len(body["experience"]) == 1


def test_verification_survives_unchanged_rows_and_clears_on_change(world, make_user):
    steward = make_user("steward", "Data steward")
    c = api(steward)
    row = put(c, world, {"skills": [{"skill_id": str(world["cook"].pk), "proficiency": 2}]}).json()[
        "skills"
    ][0]
    assert row["verified"] is False
    v = c.post(
        world["url"] + "/verify",
        {"kind": "skill", "id": row["id"], "verified": True},
        content_type="application/json",
    ).json()
    assert v["skills"][0]["verified"] and v["skills"][0]["verified_by"] == "steward"
    same = put(
        c,
        world,
        {"skills": [{"id": row["id"], "skill_id": str(world["cook"].pk), "proficiency": 2}]},
    ).json()
    assert same["skills"][0]["verified"] is True
    changed = put(
        c,
        world,
        {"skills": [{"id": row["id"], "skill_id": str(world["cook"].pk), "proficiency": 3}]},
    ).json()
    assert changed["skills"][0]["verified"] is False and changed["skills"][0]["id"] == row["id"]


def test_bad_input_is_rejected_with_a_clear_field(world, make_user):
    c = api(make_user("steward", "Data steward"))
    dup = put(
        c,
        world,
        {"skills": [{"skill_id": str(world["cook"].pk)}, {"skill_id": str(world["cook"].pk)}]},
    )
    assert dup.status_code == 400 and any(e["field"] == "skills" for e in dup.json()["errors"])
    retired = Skill.objects.create(code="OLD", name="Old skill", active=False)
    assert put(c, world, {"skills": [{"skill_id": str(retired.pk)}]}).status_code == 400
    r = put(c, world, {"readiness": {"work_patterns": ["moonlighting"]}})
    assert r.status_code == 400
    assert put(c, world, {"experience": [{"role_title": "x", "months": -1}]}).status_code == 400
    assert not ParticipantSkill.objects.exists()


def test_permissions_and_scope(world, make_user):
    manager = make_user("mgr", "Manager")  # can view the profile, cannot edit it
    assert api(manager).get(world["url"]).status_code in (200, 404)
    assert put(api(manager), world, {"skills": []}).status_code == 403
    nobody = make_user("analyst", "M&E analyst")
    assert api(nobody).get(world["url"]).status_code == 403
    officer = make_user("officer", "Placement officer")  # assigned scope: not their youth
    assert api(officer).get(world["url"]).status_code == 404
    assert put(api(officer), world, {"skills": []}).status_code == 404


def test_merge_carries_the_profile_across_and_undo_puts_it_back(world, make_user):
    from apps.participants import duplicates, profile
    from apps.participants.models import DuplicateCandidate

    steward = make_user("steward", "Data steward")
    survivor = world["p"]
    absorbed = Participant.objects.create(full_name_source="Profile Person")
    profile.write(
        actor=steward,
        p=absorbed,
        data={
            "skills": [{"skill_id": str(world["cook"].pk)}],
            "experience": [{"role_title": "Cook", "months": 5}],
            "readiness": {"work_patterns": ["part_time"]},
        },
    )
    profile.write(actor=steward, p=survivor, data={"skills": [{"skill_id": str(world["cook"].pk)}]})
    cand = DuplicateCandidate.objects.create(
        participant_a=survivor, participant_b=absorbed, score=0.9, reasons=[]
    )
    record = duplicates.merge(
        actor=steward, candidate=cand, survivor_id=survivor.pk, reason="same person"
    )
    got = profile.read(survivor)
    assert got["summary"]["experience_months"] == 5
    assert got["readiness"]["work_patterns"] == ["part_time"]
    assert len(got["skills"]) == 1  # the clashing skill stayed behind
    duplicates.unmerge(actor=steward, merge_record=record, reason="mistake")
    assert profile.read(survivor)["summary"]["experience_months"] == 0
    assert profile.read(absorbed)["summary"]["experience_months"] == 5


def test_youth_can_be_created_with_capability_in_one_step(db, make_user):
    c = api(make_user("steward", "Data steward"))
    cook = Skill.objects.get(code="SK-FOOD")
    level = QualificationLevel.objects.get(code="QL05")
    r = c.post(
        "/api/v1/participants",
        {
            "full_name_source": "New Capable",
            "capability": {
                "qualifications": [{"level_id": str(level.pk), "title": "Diploma"}],
                "skills": [{"skill_id": str(cook.pk), "proficiency": 2}],
                "experience": [{"role_title": "Cook", "months": 6}],
                "readiness": {"available_from": "2026-12-01", "work_patterns": ["full_time"]},
            },
        },
        content_type="application/json",
    )
    assert r.status_code == 201, r.content
    p = Participant.objects.get(full_name_source="New Capable")
    got = c.get(f"/api/v1/participants/{p.pk}/profile").json()
    assert got["summary"]["highest_qualification"] == level.name
    assert got["summary"]["experience_months"] == 6 and got["skills"][0]["skill_id"] == str(cook.pk)

    bad = c.post(
        "/api/v1/participants",
        {
            "full_name_source": "Bad Capable",
            "capability": {"skills": [{"skill_id": "11111111-1111-1111-1111-111111111111"}]},
        },
        content_type="application/json",
    )
    assert bad.status_code == 400
    assert not Participant.objects.filter(full_name_source="Bad Capable").exists()  # all or nothing
    opts = c.get("/api/v1/participants/profile-options").json()
    assert {"levels", "skills", "sectors", "work_patterns"} <= set(opts)
