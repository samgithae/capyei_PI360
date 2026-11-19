"""Stakeholder reports (Insight > Reports): the five report pages and their PDF and Excel files.

Acceptance: with no filters a report matches the dashboard; each filter narrows the figures; a bad
filter is a 400, never ignored; scope applies; the files open and repeat the page; the audit entry
holds counts and filters, never a name."""

import io
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from openpyxl import load_workbook

from apps.audit.models import AuditEvent
from apps.employers.models import Employer, Opportunity
from apps.identity import services as identity
from apps.participants.models import Participant
from apps.referrals.models import Referral, StageEvent

from .test_participants import enrol, world  # noqa: F401

JSON = "application/json"
BASE = "/api/v1/reporting/reports"
DASH = "/api/v1/reporting/dashboard"
SLUGS = [
    "programme-scorecard",
    "placement-outcomes",
    "equity-and-reach",
    "retention",
    "employer-pipeline",
]


def client_for(user):
    c = Client()
    c.force_login(user)
    return c


def today():
    return timezone.localdate()


@pytest.fixture
def officer(make_user):
    user = make_user("wanjiru", "Placement officer")
    identity.set_scopes(actor=None, user=user, scopes=[("officer", "self")])
    return user


@pytest.fixture
def admin(make_user):
    return make_user("admin", "Administrator")


@pytest.fixture
def analyst(make_user):
    return make_user("analyst", "M&E analyst")


@pytest.fixture
def data(world, officer):  # noqa: F811
    """Three youth: Ann (officer's, programme one, placed), Bea (officer's, programme two,
    referred), Cy (someone else's, programme one, not referred)."""
    ann = Participant.objects.create(
        full_name_source="Ann Test", gender="female", assigned_officer=officer
    )
    bea = Participant.objects.create(
        full_name_source="Bea Test", gender="female", assigned_officer=officer
    )
    cy = Participant.objects.create(full_name_source="Cy Test", gender="male")
    for person, idx in ((ann, 0), (bea, 1), (cy, 0)):
        enrol(world, person, idx)
    emp = Employer.objects.create(name="Acme Foods")
    opp = Opportunity.objects.create(employer=emp, title="Cook", status="open")
    Opportunity.objects.create(employer=emp, title="Baker", status="open")
    c = client_for(officer)
    r = c.post(
        "/api/v1/placements",
        {
            "participant_id": str(ann.pk), "pathway": "wage", "employer_name_source": "Acme Foods",
            "start_date": (today() - timedelta(days=100)).isoformat(),
        },
        content_type=JSON,
    )  # fmt: skip
    assert r.status_code == 201, r.content
    ref = Referral.objects.create(
        participant=bea, opportunity=opp, stage="submitted",
        referred_at=timezone.now() - timedelta(days=90),
    )  # fmt: skip
    StageEvent.objects.create(
        referral=ref, from_stage="draft", to_stage="submitted", at=ref.referred_at, actor_label="t"
    )
    Referral.objects.filter(pk=ref.pk).update(updated_at=timezone.now() - timedelta(days=90))
    return {"ann": ann, "bea": bea, "cy": cy, "world": world, "client": c}


def get(c, slug, **params):
    return c.get(f"{BASE}/{slug}", params)


def tile(body, key):
    return next(t for t in body["tiles"] if t["id"] == key)["value"]


def test_the_index_and_options_open_to_report_viewers_only(data, analyst, make_user):
    body = client_for(analyst).get(BASE).json()
    assert [r["slug"] for r in body["reports"]] == SLUGS
    opts = client_for(analyst).get(f"{BASE}/filters").json()
    assert {
        "programmes",
        "cohorts",
        "counties",
        "sectors",
        "employers",
        "pathways",
        "checkins",
    } <= opts.keys()
    assert [p["name"] for p in opts["programmes"]] == ["Programme One", "Programme Two"]
    assert client_for(make_user("youth", "Youth")).get(BASE).status_code == 403


@pytest.mark.parametrize("slug", SLUGS)
def test_every_report_builds_with_and_without_data(slug, admin, db):
    body = get(client_for(admin), slug).json()
    assert body["slug"] == slug and body["tiles"] and body["definitions"]
    assert {"charts", "tables", "notes", "filters_applied", "generated_on"} <= body.keys()


@pytest.mark.parametrize("slug", SLUGS)
def test_every_report_builds_over_real_looking_data(slug, data, admin):
    body = get(client_for(admin), slug).json()
    assert body["tiles"] and all({"id", "label", "value"} <= t.keys() for t in body["tiles"])
    for ch in body["charts"]:
        assert all(len(s["values"]) == len(ch["categories"]) for s in ch["series"])
    for t in body["tables"]:
        assert all(len(r) == len(t["columns"]) for r in t["rows"])


def test_the_scorecard_matches_the_dashboard(data, admin):
    c = client_for(admin)
    dash = c.get(DASH, {"period": "all"}).json()["tiles"]
    body = get(c, "programme-scorecard").json()
    assert tile(body, "registered") == dash["registered"] == 3
    assert tile(body, "referred") == dash["referred"] == 1
    assert tile(body, "placed") == dash["placed"] == 1
    assert tile(body, "rate") == dash["placement_rate"]


def test_filters_narrow_the_figures(data, admin):
    c, w = client_for(admin), data["world"]
    one = str(w["progs"][0].pk)
    assert tile(get(c, "programme-scorecard", programme=one).json(), "registered") == 2
    assert tile(get(c, "programme-scorecard", gender="male").json(), "registered") == 1
    cohort = str(w["ccs"][1].cohort_id)
    scoped = get(c, "programme-scorecard", cohort=cohort).json()
    assert tile(scoped, "registered") == 1 and tile(scoped, "placed") == 0
    assert scoped["filters_applied"] == [{"key": "cohort", "label": "Cohort", "value": "Cohort 2"}]
    assert tile(get(c, "placement-outcomes", pathway="wage").json(), "youth") == 1
    assert tile(get(c, "placement-outcomes", pathway="further_training").json(), "youth") == 0
    year = today().year
    inside = get(c, "placement-outcomes", **{"from": f"{year - 1}-01-01", "to": f"{year}-12-31"})
    assert tile(inside.json(), "youth") == 1
    before = get(c, "placement-outcomes", **{"to": "2000-01-01"}).json()
    assert tile(before, "youth") == 0 and before["charts"][0]["categories"] == []
    assert tile(get(c, "equity-and-reach", programme=one).json(), "women-registered") == 50.0
    pipeline = get(c, "employer-pipeline").json()
    assert tile(pipeline, "referrals") == 1 and tile(pipeline, "stalled") == 1
    assert tile(get(c, "employer-pipeline", stage="placed").json(), "referrals") == 0


def test_a_filter_the_report_does_not_offer_is_not_applied(data, admin):
    body = get(
        client_for(admin), "equity-and-reach", employer="00000000-0000-0000-0000-000000000000"
    )
    assert body.status_code == 200 and body.json()["filters_applied"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2022-13-01"},
        {"from": "2023-01-01", "to": "2022-01-01"},
        {"programme": "not-an-id"},
        {"gender": "robot"},
        {"pathway": "teleport"},
        {"checkin": "soon"},
    ],
)
def test_a_bad_filter_is_a_400_and_never_ignored(params, admin, db):
    r = get(client_for(admin), "programme-scorecard", **params)
    assert r.status_code == 400 and r.json()["errors"][0]["message"]
    r = get(client_for(admin), "retention", **params)
    assert r.status_code in (200, 400)


def test_an_unknown_report_is_not_found(admin, db):
    assert get(client_for(admin), "nope").status_code == 404
    assert client_for(admin).post(f"{BASE}/nope/export?file_format=pdf").status_code == 404


def test_an_officer_sees_only_their_own_youth(data, officer, admin):
    own = get(client_for(officer), "programme-scorecard").json()
    assert tile(own, "registered") == 2
    assert tile(get(client_for(admin), "programme-scorecard").json(), "registered") == 3


def test_the_analyst_sees_the_numbers_without_a_name(data, analyst):
    body = get(client_for(analyst), "programme-scorecard")
    assert body.status_code == 200 and tile(body.json(), "registered") == 3
    for name in ("Ann", "Bea", "Cy Test"):
        assert name not in body.content.decode()


def test_retention_waits_for_enough_check_ins(data, admin):
    c = data["client"]
    rows = c.get("/api/v1/followups", {"kind": "early"}).json()["results"]
    pk = rows[0]["id"]
    done = c.post(
        f"/api/v1/followups/{pk}/complete",
        {"still_employed": True, "evidence_source": "phone_call"},
        content_type=JSON,
    )
    assert done.status_code == 200, done.content
    body = get(client_for(admin), "retention").json()
    assert tile(body, "done") == 1 and tile(body, "placements") == 1
    assert tile(body, "retention") is None  # one call is not a trend
    assert body["tiles"][2]["hint"].startswith("Shown once at least")
    assert tile(get(client_for(admin), "retention", checkin="90").json(), "done") == 1
    assert tile(get(client_for(admin), "retention", checkin="30").json(), "done") == 0


@pytest.mark.parametrize("slug", SLUGS)
def test_excel_file_opens_and_repeats_the_page(slug, data, admin):
    c = client_for(admin)
    r = c.post(f"{BASE}/{slug}/export?file_format=xlsx")
    assert r.status_code == 200 and "spreadsheetml" in r["Content-Type"]
    assert f"{slug}-" in r["Content-Disposition"] and r["Cache-Control"] == "no-store"
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[0] == "Summary" and wb.sheetnames[-1] == "Definitions"
    page = get(c, slug).json()
    summary = {row[0].value: row[1].value for row in wb["Summary"].iter_rows() if row[0].value}
    first = page["tiles"][0]
    assert summary[first["label"]] == (
        first["value"] if first["value"] is not None else "Not enough data"
    )


@pytest.mark.parametrize("slug", SLUGS)
def test_pdf_file_is_a_pdf(slug, data, admin):
    r = client_for(admin).post(f"{BASE}/{slug}/export?file_format=pdf&gender=female")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and len(r.content) > 2000


def test_a_file_follows_the_filters_on_the_page(data, admin):
    r = client_for(admin).post(f"{BASE}/programme-scorecard/export?file_format=xlsx&gender=male")
    wb = load_workbook(io.BytesIO(r.content))
    summary = {row[0].value: row[1].value for row in wb["Summary"].iter_rows() if row[0].value}
    assert summary["Gender"] == "Male" and summary["Youth in scope"] == 1


def test_export_rejects_a_bad_format_or_filter(data, admin):
    c = client_for(admin)
    assert c.post(f"{BASE}/retention/export?file_format=docx").status_code == 400
    assert c.post(f"{BASE}/retention/export").status_code == 400
    assert c.post(f"{BASE}/retention/export?file_format=pdf&checkin=x").status_code == 400
    assert not AuditEvent.objects.filter(action="report.exported").exists()


def test_an_export_is_audited_without_names(data, admin):
    r = client_for(admin).post(f"{BASE}/placement-outcomes/export?file_format=xlsx&pathway=wage")
    assert r.status_code == 200
    event = AuditEvent.objects.get(action="report.exported")
    assert event.object_id == "placement-outcomes" and event.actor_id == admin.pk
    assert event.after["format"] == "xlsx" and event.after["filters"] == {
        "pathway": "Wage employment"
    }
    assert isinstance(event.after["rows"], int)
    blob = str(event.after)
    assert not any(n in blob for n in ("Ann", "Bea", "Cy Test"))


def test_a_formula_cannot_hide_in_a_cell(data, admin):
    from apps.reporting import report_files

    report = {
        "slug": "x", "title": "T", "purpose": "p", "generated_on": "2026-01-01",
        "filters_applied": [], "tiles": [], "charts": [], "notes": [],
        "tables": [{"id": "t", "title": "T", "columns": ["A"], "rows": [["=HYPERLINK(1)"]]}],
        "definitions": [],
    }  # fmt: skip
    wb = load_workbook(io.BytesIO(report_files.xlsx(report)))
    assert wb["T"]["A4"].value == "'=HYPERLINK(1)"
