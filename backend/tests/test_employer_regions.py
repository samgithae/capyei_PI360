"""Employers and opportunities with many counties and many sectors. Synthetic data only.

The rule under test: an employer works in several counties and sectors; an opportunity may only
use a subset of its employer's, and the API (not just the form) enforces it."""

from datetime import date, timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client

from apps.configuration.models import County, Sector
from apps.employers import services
from apps.employers.models import Employer, Opportunity

EMP = "/api/v1/employers"
OPP = "/api/v1/opportunities"
JSON = "application/json"


@pytest.fixture
def c(make_user):
    cl = Client()
    cl.force_login(make_user("steward", "Data steward"))
    return cl


@pytest.fixture
def places(db):
    return {
        "nairobi": County.objects.get(name="Nairobi"),
        "mombasa": County.objects.get(name="Mombasa"),
        "kisumu": County.objects.get(name="Kisumu"),
        "hospitality": Sector.objects.create(code="HOSP", name="Hospitality"),
        "ict": Sector.objects.create(code="ICT", name="ICT"),
        "retail": Sector.objects.create(code="RETAIL", name="Retail"),
    }


def ids(*rows):
    return [str(r.pk) for r in rows]


def make_employer(c, places, **kw):
    body = {
        "name": "Coast Hotels",
        "county_ids": ids(places["nairobi"], places["mombasa"]),
        "sector_ids": ids(places["hospitality"], places["ict"]),
        **kw,
    }
    r = c.post(EMP, body, content_type=JSON)
    assert r.status_code == 201, r.content
    return r.json()


def make_opportunity(c, employer, **kw):
    body = {"employer_id": employer["id"], "title": "Front desk", **kw}
    return c.post(OPP, body, content_type=JSON)


def names(rows):
    return sorted(r["name"] for r in rows)


# --- 1. employer profile -------------------------------------------------------------------


def test_employer_keeps_all_four_links_and_reopens_with_them(c, places):
    created = make_employer(c, places)
    body = c.get(f"{EMP}/{created['id']}").json()
    assert names(body["counties"]) == ["Mombasa", "Nairobi"]
    assert names(body["sectors"]) == ["Hospitality", "ICT"]
    assert sorted(body["county_ids"]) == sorted(ids(places["nairobi"], places["mombasa"]))
    assert len(body["sector_ids"]) == 2


def test_duplicate_ids_are_normalised_not_stored_twice(c, places):
    nairobi = str(places["nairobi"].pk)
    made = make_employer(c, places, county_ids=[nairobi, nairobi, nairobi])
    assert [x["name"] for x in made["counties"]] == ["Nairobi"]
    assert Employer.objects.get(pk=made["id"]).counties.count() == 1


def test_unknown_inactive_and_malformed_ids_are_refused(c, places):
    ghost = "00000000-0000-0000-0000-000000000000"
    r = c.post(EMP, {"name": "A", "county_ids": [ghost]}, content_type=JSON)
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "unknown"
    places["retail"].active = False
    places["retail"].save()
    r = c.post(EMP, {"name": "B", "sector_ids": ids(places["retail"])}, content_type=JSON)
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "inactive"
    r = c.post(EMP, {"name": "C", "county_ids": ["not-a-uuid"]}, content_type=JSON)
    assert r.status_code == 400
    assert Employer.objects.count() == 0


def test_employer_links_are_optional_and_can_be_edited_and_emptied(c, places):
    bare = c.post(EMP, {"name": "No Places"}, content_type=JSON).json()
    assert bare["counties"] == [] and bare["sectors"] == []
    made = make_employer(c, places)
    r = c.patch(
        f"{EMP}/{made['id']}",
        {"county_ids": ids(places["kisumu"]), "sector_ids": ids(places["retail"])},
        content_type=JSON,
    )
    assert r.status_code == 200
    assert names(r.json()["counties"]) == ["Kisumu"] and names(r.json()["sectors"]) == ["Retail"]
    # a PATCH that leaves the links out does not touch them
    r = c.patch(f"{EMP}/{made['id']}", {"notes": "x"}, content_type=JSON)
    assert names(r.json()["counties"]) == ["Kisumu"]
    r = c.patch(f"{EMP}/{made['id']}", {"county_ids": []}, content_type=JSON)
    assert r.json()["counties"] == []


def test_employer_edit_is_audited_with_before_and_after_ids(c, places):
    made = make_employer(c, places)
    c.patch(f"{EMP}/{made['id']}", {"county_ids": ids(places["nairobi"])}, content_type=JSON)
    latest = c.get(f"{EMP}/{made['id']}/history").json()[0]
    assert latest["action"] == "employer.updated"
    assert len(latest["before"]["county_ids"]) == 2 and len(latest["after"]["county_ids"]) == 1


def test_list_filters_by_county_and_sector(c, places):
    make_employer(c, places)
    make_employer(
        c, places, name="Lake Retail", county_ids=ids(places["kisumu"]),
        sector_ids=ids(places["retail"]),
    )  # fmt: skip
    by_county = c.get(EMP, {"county": str(places["mombasa"].pk)}).json()
    assert [e["name"] for e in by_county["results"]] == ["Coast Hotels"]
    by_sector = c.get(EMP, {"sector": str(places["retail"].pk)}).json()
    assert [e["name"] for e in by_sector["results"]] == ["Lake Retail"]


# --- 2. opportunity creation ---------------------------------------------------------------


def test_opportunity_stores_chosen_subset_and_returns_it(c, places):
    emp = make_employer(c, places)
    r = make_opportunity(
        c, emp, county_ids=ids(places["nairobi"]), sector_ids=ids(places["hospitality"])
    )
    assert r.status_code == 201, r.content
    body = c.get(f"{OPP}/{r.json()['id']}").json()
    assert names(body["counties"]) == ["Nairobi"] and names(body["sectors"]) == ["Hospitality"]
    assert body["county_ids"] == ids(places["nairobi"])
    assert Opportunity.objects.get(pk=body["id"]).counties.count() == 1


def test_opportunity_may_leave_counties_and_sectors_empty(c, places):
    emp = make_employer(c, places)
    body = make_opportunity(c, emp).json()
    assert body["counties"] == [] and body["sectors"] == []


# --- 4. backend rejects what the employer does not have ------------------------------------


def test_create_rejects_county_and_sector_not_belonging_to_employer(c, places):
    emp = make_employer(c, places)
    r = make_opportunity(c, emp, county_ids=ids(places["kisumu"]))
    assert r.status_code == 409
    err = r.json()["errors"][0]
    assert err["field"] == "county_ids" and err["code"] == "county_not_in_employer"
    assert "Kisumu" in err["message"] and "Coast Hotels" in err["message"]
    assert "employer profile" in err["message"]
    r = make_opportunity(c, emp, sector_ids=ids(places["retail"]))
    err = r.json()["errors"][0]
    assert r.status_code == 409 and err["field"] == "sector_ids"
    assert err["code"] == "sector_not_in_employer" and "Retail" in err["message"]
    assert Opportunity.objects.count() == 0


def test_create_rejects_unknown_ids_and_normalises_duplicates(c, places):
    emp = make_employer(c, places)
    ghost = "00000000-0000-0000-0000-000000000000"
    assert make_opportunity(c, emp, county_ids=[ghost]).json()["errors"][0]["code"] == "unknown"
    n = str(places["nairobi"].pk)
    body = make_opportunity(c, emp, county_ids=[n, n]).json()
    assert [x["name"] for x in body["counties"]] == ["Nairobi"]


def test_employer_without_links_cannot_have_opportunity_links(c, places):
    bare = c.post(EMP, {"name": "No Places"}, content_type=JSON).json()
    r = make_opportunity(c, bare, county_ids=ids(places["nairobi"]))
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "county_not_in_employer"


def test_update_rejects_outside_values_and_accepts_inside_ones(c, places):
    emp = make_employer(c, places)
    oid = make_opportunity(c, emp, county_ids=ids(places["nairobi"])).json()["id"]
    r = c.patch(f"{OPP}/{oid}", {"county_ids": ids(places["kisumu"])}, content_type=JSON)
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "county_not_in_employer"
    r = c.patch(f"{OPP}/{oid}", {"sector_ids": ids(places["retail"])}, content_type=JSON)
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "sector_not_in_employer"
    r = c.patch(
        f"{OPP}/{oid}",
        {"county_ids": ids(places["mombasa"], places["nairobi"]), "sector_ids": ids(places["ict"])},
        content_type=JSON,
    )
    assert r.status_code == 200
    assert names(r.json()["counties"]) == ["Mombasa", "Nairobi"]
    assert names(r.json()["sectors"]) == ["ICT"]
    # unchanged links survive an unrelated edit
    r = c.patch(f"{OPP}/{oid}", {"title": "Receptionist"}, content_type=JSON)
    assert names(r.json()["counties"]) == ["Mombasa", "Nairobi"]


# --- 3. switching employer -----------------------------------------------------------------


def test_changing_a_draft_opportunitys_employer_revalidates_its_links(c, places):
    coast = make_employer(c, places)
    lake = make_employer(
        c, places, name="Lake Retail", county_ids=ids(places["kisumu"], places["nairobi"]),
        sector_ids=ids(places["retail"]),
    )  # fmt: skip
    oid = make_opportunity(
        c, coast, county_ids=ids(places["nairobi"], places["mombasa"]),
        sector_ids=ids(places["hospitality"]),
    ).json()["id"]  # fmt: skip
    # moving with the old links left in place is refused: Mombasa and Hospitality are not Lake's
    r = c.patch(f"{OPP}/{oid}", {"employer_id": lake["id"]}, content_type=JSON)
    assert r.status_code == 409
    assert Opportunity.objects.get(pk=oid).employer_id.hex == coast["id"].replace("-", "")
    # moving with the links cleared or re-chosen works
    r = c.patch(
        f"{OPP}/{oid}",
        {
            "employer_id": lake["id"], "county_ids": ids(places["nairobi"]),
            "sector_ids": ids(places["retail"]),
        },
        content_type=JSON,
    )  # fmt: skip
    assert r.status_code == 200, r.content
    assert r.json()["employer_id"] == lake["id"]
    assert names(r.json()["counties"]) == ["Nairobi"] and names(r.json()["sectors"]) == ["Retail"]


def test_employer_cannot_change_once_the_opportunity_is_no_longer_a_draft(c, places):
    coast = make_employer(c, places)
    other = make_employer(c, places, name="Other Hotels")
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    oid = make_opportunity(c, coast, closing_date=tomorrow).json()["id"]
    c.post(f"{OPP}/{oid}/transition", {"to": "open"}, content_type=JSON)
    r = c.patch(f"{OPP}/{oid}", {"employer_id": other["id"]}, content_type=JSON)
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "employer_locked"


# --- 5. editing the employer after opportunities exist -------------------------------------


def test_employer_cannot_drop_a_county_a_live_opportunity_uses(c, places):
    emp = make_employer(c, places)
    make_opportunity(c, emp, county_ids=ids(places["mombasa"]))
    r = c.patch(f"{EMP}/{emp['id']}", {"county_ids": ids(places["nairobi"])}, content_type=JSON)
    assert r.status_code == 409
    err = r.json()["errors"][0]
    assert (
        err["code"] == "in_use" and "Mombasa" in err["message"] and "Front desk" in err["message"]
    )
    # an unused county can be dropped
    r = c.patch(f"{EMP}/{emp['id']}", {"county_ids": ids(places["mombasa"])}, content_type=JSON)
    assert r.status_code == 200 and names(r.json()["counties"]) == ["Mombasa"]


def test_closed_opportunities_do_not_block_removal_and_keep_their_history(c, places):
    emp = make_employer(c, places)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    oid = make_opportunity(c, emp, county_ids=ids(places["mombasa"]), closing_date=tomorrow).json()[
        "id"
    ]
    c.post(f"{OPP}/{oid}/transition", {"to": "open"}, content_type=JSON)
    c.post(f"{OPP}/{oid}/transition", {"to": "closed"}, content_type=JSON)
    r = c.patch(f"{EMP}/{emp['id']}", {"county_ids": ids(places["nairobi"])}, content_type=JSON)
    assert r.status_code == 200
    assert names(c.get(f"{OPP}/{oid}").json()["counties"]) == ["Mombasa"]


def test_existing_opportunity_links_outside_employer_are_kept_and_loadable(c, places):
    """Older records may hold a link the employer no longer lists; editing must not choke."""
    emp = make_employer(c, places)
    opp = Opportunity.objects.create(employer_id=emp["id"], title="Legacy")
    opp.counties.set([places["kisumu"]])
    opp.sectors.set([places["retail"]])
    body = c.get(f"{OPP}/{opp.pk}").json()
    assert names(body["counties"]) == ["Kisumu"] and names(body["sectors"]) == ["Retail"]
    r = c.patch(
        f"{OPP}/{opp.pk}",
        {
            "title": "Legacy edit",
            "county_ids": body["county_ids"],
            "sector_ids": body["sector_ids"],
        },
        content_type=JSON,
    )
    assert r.status_code == 200 and names(r.json()["counties"]) == ["Kisumu"]


# --- matching, reporting and referrals still read the new shape ----------------------------


def test_matching_and_reporting_inputs_expose_every_county_and_sector(c, places):
    emp = make_employer(c, places)
    oid = make_opportunity(
        c, emp, county_ids=ids(places["nairobi"], places["mombasa"]),
        sector_ids=ids(places["hospitality"], places["ict"]),
    ).json()["id"]  # fmt: skip
    inputs = services.compatibility_inputs(oid)
    assert sorted(inputs["sector_ids"]) == sorted(ids(places["hospitality"], places["ict"]))
    facts = services.report_facts()
    assert len(facts["opportunities"][0]["county_ids"]) == 2
    assert len(facts["employers"][0]["county_ids"]) == 2
    assert services.county_names(Opportunity.objects.get(pk=oid)) == "Mombasa, Nairobi"


# --- data migration ------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_migration_carries_single_values_forward_and_invents_nothing():
    before = [("employers", "0006_requirement_min_grade")]
    after = [("employers", "0009_drop_single_county_sector")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old = executor.loader.project_state(before).apps
    County_, Sector_ = (
        old.get_model("configuration", "County"),
        old.get_model("configuration", "Sector"),
    )
    Employer_, Opportunity_ = (
        old.get_model("employers", "Employer"),
        old.get_model("employers", "Opportunity"),
    )
    nairobi, mombasa = County_.objects.get(name="Nairobi"), County_.objects.get(name="Mombasa")
    sector = Sector_.objects.create(code="MIG", name="Migration sector")
    full = Employer_.objects.create(name="Has both", county=nairobi, sector=sector)
    half = Employer_.objects.create(name="County only", county=mombasa)
    none = Employer_.objects.create(name="Neither")
    opp = Opportunity_.objects.create(employer=full, title="T", county=nairobi, sector=sector)
    bare = Opportunity_.objects.create(employer=none, title="Bare")

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    new = executor.loader.project_state(after).apps
    Emp, Opp = new.get_model("employers", "Employer"), new.get_model("employers", "Opportunity")
    assert list(Emp.objects.get(pk=full.pk).counties.values_list("name", flat=True)) == ["Nairobi"]
    assert list(Emp.objects.get(pk=full.pk).sectors.values_list("name", flat=True)) == [
        "Migration sector"
    ]
    assert list(Emp.objects.get(pk=half.pk).counties.values_list("name", flat=True)) == ["Mombasa"]
    assert Emp.objects.get(pk=half.pk).sectors.count() == 0
    assert Emp.objects.get(pk=none.pk).counties.count() == 0
    assert (
        Opp.objects.get(pk=opp.pk).counties.count() == 1
        and Opp.objects.get(pk=opp.pk).sectors.count() == 1
    )
    assert (
        Opp.objects.get(pk=bare.pk).counties.count() == 0
        and Opp.objects.get(pk=bare.pk).sectors.count() == 0
    )
    assert Emp.objects.count() == 3 and Opp.objects.count() == 2  # no row lost

    # and back: the first link returns to the single column
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    back = executor.loader.project_state(before).apps
    assert back.get_model("employers", "Employer").objects.get(pk=full.pk).county_id == nairobi.pk
    assert back.get_model("employers", "Employer").objects.get(pk=none.pk).county_id is None
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
