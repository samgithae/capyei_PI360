"""The skills picker on an opportunity: search, categories, popular, adding a missing skill, and
saving the whole selection. Synthetic data only."""

import pytest
from django.test import Client

from apps.configuration.models import County, Sector, Skill
from apps.employers.models import Opportunity, OpportunityRequirement

SK = "/api/v1/requirement-skills"
OPP = "/api/v1/opportunities"
JSON = "application/json"


@pytest.fixture
def c(make_user):
    cl = Client()
    cl.force_login(make_user("officer", "Placement officer"))
    return cl


@pytest.fixture
def skills(db):
    Skill.objects.all().delete()
    make = {}
    for code, name, cat in (
        ("A1", "Welding", "Trades"),
        ("A2", "Plumbing", "Trades"),
        ("A3", "Customer service", "Customer & sales"),
        ("A4", "Sales", "Customer & sales"),
        ("A5", "Bookkeeping", "Office"),
        ("A6", "Telephone manners", ""),
    ):
        make[name] = Skill.objects.create(code=code, name=name, category=cat)
    return make


@pytest.fixture
def opp(c, db):
    sector = Sector.objects.create(code="S", name="Trade")
    county = County.objects.get(name="Nairobi")
    emp = c.post(
        "/api/v1/employers",
        {"name": "Acme", "county_ids": [str(county.pk)], "sector_ids": [str(sector.pk)]},
        content_type=JSON,
    ).json()
    r = c.post(OPP, {"employer_id": emp["id"], "title": "Welder"}, content_type=JSON)
    assert r.status_code == 201, r.content
    return r.json()


def names(resp):
    return [r["name"] for r in resp.json()["results"]]


def sync(c, opp, *items):
    return c.put(
        f"{OPP}/{opp['id']}/requirements/skills", {"skills": list(items)}, content_type=JSON
    )


def item(skill, mandatory=False):
    return {"skill_id": str(skill.pk), "is_mandatory": mandatory}


# --- search, categories, popular -----------------------------------------------------------------


def test_search_is_partial_and_any_case(c, skills):
    assert names(c.get(SK, {"q": "WELD"})) == ["Welding"]
    assert names(c.get(SK, {"q": "ervic"})) == ["Customer service"]
    assert c.get(SK, {"q": "nothing like this"}).json() == {"total": 0, "results": []}


def test_search_puts_names_that_start_with_the_text_first(c, skills):
    names_ = names(c.get(SK, {"q": "s"}))
    assert names_[0] == "Sales"


def test_search_pages_on_the_server(c, skills):
    first = c.get(SK, {"limit": 2}).json()
    assert first["total"] == 6 and len(first["results"]) == 2
    rest = c.get(SK, {"limit": 2, "offset": 4}).json()
    assert [r["name"] for r in rest["results"]] == ["Telephone manners", "Welding"]


def test_search_inside_one_category(c, skills):
    assert names(c.get(SK, {"category": "Trades"})) == ["Plumbing", "Welding"]
    assert names(c.get(SK, {"category": "Other"})) == ["Telephone manners"]


def test_categories_count_their_skills_and_put_other_last(c, skills):
    rows = c.get(f"{SK}/categories").json()["results"]
    assert rows == [
        {"name": "Customer & sales", "count": 2},
        {"name": "Office", "count": 1},
        {"name": "Trades", "count": 2},
        {"name": "Other", "count": 1},
    ]


def test_retired_skills_are_not_offered(c, skills):
    skills["Welding"].active = False
    skills["Welding"].save()
    assert "Welding" not in names(c.get(SK))


def test_popular_follows_real_use_then_tops_up(c, skills, opp):
    sync(c, opp, item(skills["Sales"]), item(skills["Welding"]))
    rows = c.get(f"{SK}/popular").json()["results"]
    assert {r["name"] for r in rows[:2]} == {"Sales", "Welding"}
    assert all(r["used"] == 1 for r in rows[:2])
    assert len(rows) == 6 and all(r["used"] == 0 for r in rows[2:])


# --- adding a skill ------------------------------------------------------------------------------


def add(c, name, category="", **kw):
    return c.post(f"{SK}/add", {"name": name, "category": category, **kw}, content_type=JSON)


def test_add_a_missing_skill_into_an_existing_category(c, skills):
    r = add(c, "  forklift   operation ", "Trades")
    assert r.status_code == 201, r.content
    assert r.json()["name"] == "Forklift operation" and r.json()["category"] == "Trades"
    assert names(c.get(SK, {"q": "forklift"})) == ["Forklift operation"]  # reused from now on


def test_add_into_other_leaves_the_category_empty(c, skills):
    r = add(c, "Beekeeping", "Other")
    assert r.status_code == 201 and r.json()["category"] == "Other"
    assert Skill.objects.get(name="Beekeeping").category == ""


def test_add_refuses_an_unknown_category(c, skills):
    r = add(c, "Beekeeping", "Made up")
    assert r.status_code == 409 and r.json()["errors"][0]["field"] == "category"


def test_add_refuses_the_same_name_in_any_spelling(c, skills):
    r = add(c, "WELDING!")
    assert r.status_code == 409
    body = r.json()
    assert body["errors"][0]["code"] == "exists" and body["existing"]["name"] == "Welding"
    assert Skill.objects.filter(name__icontains="weld").count() == 1


def test_add_asks_before_creating_a_look_alike(c, skills):
    r = add(c, "Customer care")
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "similar"
    assert [s["name"] for s in r.json()["similar"]] == ["Customer service"]
    assert not Skill.objects.filter(name="Customer care").exists()
    assert add(c, "Customer care", confirm_similar=True).status_code == 201


def test_add_refuses_a_retired_name_and_a_blank_name(c, skills):
    skills["Welding"].active = False
    skills["Welding"].save()
    assert add(c, "Welding").status_code == 409
    assert add(c, "  ").status_code == 400  # blank


def test_add_is_audited(c, skills):
    from apps.audit.models import AuditEvent

    add(c, "Beekeeping")
    assert AuditEvent.objects.filter(action="reference.created").exists()


def test_a_youth_cannot_search_or_add(make_user, skills):
    cl = Client()
    cl.force_login(make_user("kid", "Youth"))
    assert cl.get(SK).status_code == 403
    assert cl.post(f"{SK}/add", {"name": "X"}, content_type=JSON).status_code == 403


# --- saving the selection -----------------------------------------------------------------------


def test_sync_saves_a_real_requirement_with_the_skill_id(c, skills, opp):
    r = sync(c, opp, item(skills["Welding"], True), item(skills["Sales"]))
    assert r.status_code == 200, r.content
    rows = OpportunityRequirement.objects.filter(opportunity_id=opp["id"])
    assert {(x.skill_id, x.is_mandatory, x.factor) for x in rows} == {
        (skills["Welding"].pk, True, "skill"),
        (skills["Sales"].pk, False, "skill"),
    }
    assert {x.description for x in rows} == {"Welding", "Sales"}


def test_sync_removes_keeps_and_updates(c, skills, opp):
    sync(c, opp, item(skills["Welding"]), item(skills["Sales"]))
    kept = OpportunityRequirement.objects.get(skill=skills["Welding"])
    r = sync(c, opp, item(skills["Welding"], True), item(skills["Plumbing"]))
    assert r.status_code == 200
    now = OpportunityRequirement.objects.filter(opportunity_id=opp["id"])
    assert {x.skill.name for x in now} == {"Welding", "Plumbing"}
    assert now.get(skill=skills["Welding"]).pk == kept.pk  # the same row, not recreated
    assert now.get(skill=skills["Welding"]).is_mandatory is True


def test_sync_counts_a_repeated_skill_once(c, skills, opp):
    assert sync(c, opp, item(skills["Welding"]), item(skills["Welding"], True)).status_code == 200
    assert OpportunityRequirement.objects.filter(opportunity_id=opp["id"]).count() == 1


def test_sync_leaves_other_kinds_of_requirement_alone(c, skills, opp):
    c.post(
        f"{OPP}/{opp['id']}/requirements",
        {"factor": "other", "description": "Own tools"},
        content_type=JSON,
    )
    sync(c, opp, item(skills["Welding"]))
    sync(c, opp)
    left = OpportunityRequirement.objects.filter(opportunity_id=opp["id"])
    assert [x.description for x in left] == ["Own tools"]


def test_sync_rejects_an_unknown_or_retired_skill(c, skills, opp):
    skills["Welding"].active = False
    skills["Welding"].save()
    assert sync(c, opp, item(skills["Welding"])).status_code == 409
    bad = {"skill_id": "00000000-0000-4000-8000-000000000000", "is_mandatory": False}
    assert sync(c, opp, bad).status_code == 409
    assert not OpportunityRequirement.objects.filter(opportunity_id=opp["id"]).exists()


def test_a_single_requirement_cannot_repeat_a_skill(c, skills, opp):
    body = {"factor": "skill", "skill_id": str(skills["Welding"].pk)}
    assert c.post(f"{OPP}/{opp['id']}/requirements", body, content_type=JSON).status_code == 201
    r = c.post(f"{OPP}/{opp['id']}/requirements", body, content_type=JSON)
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "duplicate"


def test_a_closed_opportunity_cannot_change_skills(c, skills, opp):
    Opportunity.objects.filter(pk=opp["id"]).update(status=Opportunity.CLOSED)
    assert sync(c, opp, item(skills["Welding"])).status_code == 409


def test_edit_reloads_the_selection_and_names_only_its_own_skills(c, skills, opp):
    sync(c, opp, item(skills["Welding"], True))
    d = c.get(f"{OPP}/{opp['id']}").json()
    assert [(r["skill_id"], r["is_mandatory"]) for r in d["requirements"]] == [
        (str(skills["Welding"].pk), True)
    ]
    assert [s["name"] for s in d["requirement_options"]["skills"]] == ["Welding"]


def test_the_matching_engine_receives_the_saved_skills(c, skills, opp):
    from apps.employers import services

    sync(c, opp, item(skills["Welding"], True), item(skills["Sales"]))
    seen = services.compatibility_inputs(opp["id"])
    text = repr(seen)
    assert str(skills["Welding"].pk) in text and str(skills["Sales"].pk) in text
