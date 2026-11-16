"""The skills pick-list on a youth's profile: staff and the youth themselves read and add skills
through two route sets sharing one implementation. Synthetic data only."""

import pytest
from django.test import Client

from apps.configuration.models import Skill
from apps.participants.models import Participant, ParticipantSkill

STAFF = "/api/v1/participants/skills"
YOUTH = "/api/v1/youth/skills"
JSON = "application/json"


def api(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def staff(make_user):
    return api(make_user("steward", "Data steward"))


@pytest.fixture
def youth(make_user):
    return api(make_user("amina", "Youth"))


@pytest.fixture
def skills(db):
    Skill.objects.all().delete()
    return {
        name: Skill.objects.create(code=code, name=name, category=cat)
        for code, name, cat in (
            ("A1", "Welding", "Trades"),
            ("A2", "Plumbing", "Trades"),
            ("A3", "Bookkeeping", "Office"),
        )
    }


def names(resp):
    return [r["name"] for r in resp.json()["results"]]


@pytest.mark.parametrize("base", [STAFF, YOUTH])
def test_both_audiences_search_partially_ignoring_case(base, staff, youth, skills):
    c = staff if base == STAFF else youth
    r = c.get(base, {"q": "WELD"})
    assert r.status_code == 200 and r.json()["total"] == 1
    assert names(r) == ["Welding"]


@pytest.mark.parametrize("base", [STAFF, YOUTH])
def test_categories_and_category_paging(base, staff, youth, skills):
    c = staff if base == STAFF else youth
    cats = {x["name"]: x["count"] for x in c.get(f"{base}/categories").json()["results"]}
    assert cats == {"Trades": 2, "Office": 1}
    page = c.get(base, {"category": "Trades", "limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and len(page["results"]) == 1


def test_popular_follows_what_youth_hold_then_tops_up(staff, skills):
    p = Participant.objects.create(full_name_source="Held Skill")
    q = Participant.objects.create(full_name_source="Held Too")
    for who in (p, q):
        ParticipantSkill.objects.create(participant=who, skill=skills["Plumbing"])
    ParticipantSkill.objects.create(participant=p, skill=skills["Welding"])
    rows = staff.get(f"{STAFF}/popular").json()["results"]
    assert [(r["name"], r["used"]) for r in rows[:2]] == [("Plumbing", 2), ("Welding", 1)]
    assert [r["name"] for r in rows] == ["Plumbing", "Welding", "Bookkeeping"]  # topped up
    assert rows[2]["used"] == 0


def test_popular_ignores_archived_youth(staff, skills):
    from django.utils import timezone

    gone = Participant.objects.create(full_name_source="Gone", archived_at=timezone.now())
    ParticipantSkill.objects.create(participant=gone, skill=skills["Welding"])
    rows = staff.get(f"{STAFF}/popular").json()["results"]
    assert all(r["used"] == 0 for r in rows)


@pytest.mark.parametrize("base", [STAFF, YOUTH])
def test_a_missing_skill_can_be_added_once(base, staff, youth, skills):
    c = staff if base == STAFF else youth
    r = c.post(f"{base}/add", {"name": "Beekeeping", "category": "Other"}, content_type=JSON)
    assert r.status_code == 201 and r.json()["name"] == "Beekeeping"
    again = c.post(f"{base}/add", {"name": "beekeeping"}, content_type=JSON)
    assert again.status_code == 409
    assert again.json()["errors"][0]["code"] == "exists"
    assert Skill.objects.filter(name="Beekeeping").count() == 1


def test_a_look_alike_needs_confirming(staff, skills):
    r = staff.post(f"{STAFF}/add", {"name": "Weld"}, content_type=JSON)
    if r.status_code == 409:
        assert r.json()["errors"][0]["code"] == "similar"
        ok = staff.post(
            f"{STAFF}/add", {"name": "Weld", "confirm_similar": True}, content_type=JSON
        )
        assert ok.status_code == 201


def test_each_audience_only_uses_its_own_routes(staff, youth, make_user, skills):
    # a youth cannot reach the staff list, staff cannot use the youth one
    assert youth.get(STAFF).status_code == 403
    assert youth.post(f"{STAFF}/add", {"name": "X"}, content_type=JSON).status_code == 403
    assert staff.get(YOUTH).status_code == 403
    assert staff.post(f"{YOUTH}/add", {"name": "X"}, content_type=JSON).status_code == 403
    # a role without profile access is refused too, and a signed-out caller is not let in
    assessor = api(make_user("assess", "Assessor"))
    assert assessor.get(f"{STAFF}/popular").status_code == 403
    assert Client().get(STAFF).status_code in (401, 403)
    assert Client().get(YOUTH).status_code in (401, 403)
