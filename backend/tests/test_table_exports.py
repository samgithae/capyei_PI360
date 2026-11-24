"""Table export (T-071 revised): the file is the list as filtered on screen, with names. It needs
the grant-only permission and a purpose, respects record scope, is logged without row data, and is
never stored."""

import csv
import io
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from openpyxl import load_workbook

from apps.audit.models import AuditEvent
from apps.configuration.models import County
from apps.identity import services as identity
from apps.participants.models import Participant
from apps.reporting.models import ExportLog

from .test_participants import enrol, scope, world  # noqa: F401

URL = "/api/v1/exports/table/youth"
BODY = {"format": "csv", "purpose": "Mombasa follow-up list"}


def api(user):
    c = Client()
    c.force_login(user)
    return c


def grant(admin, user, days=3):
    return identity.grant_permission(
        actor=admin,
        user=user,
        permission="exports.identifiable",
        purpose="Project reporting",
        expires_at=timezone.now() + timedelta(days=days),
    )


@pytest.fixture
def people(world, make_user):  # noqa: F811
    mombasa, nairobi = County.objects.get(code="01"), County.objects.get(code="02")
    rows = [
        ("Amina Hassan", mombasa, "active", 0),
        ("Baraka Omar", mombasa, "withdrawn", 0),
        ("=HYPERLINK(1)", mombasa, "active", 1),  # looks like a formula
        ("Chege Maina", nairobi, "active", 0),
    ]
    for name, county, status, idx in rows:
        p = Participant.objects.create(
            full_name_source=name, origin_county=county, status=status, gender="female"
        )
        enrol(world, p, idx)
    admin = make_user("adm", "Administrator")
    grant(admin, admin)
    return {"admin": admin, "mombasa": mombasa, "world": world}


def parse(resp):
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


@pytest.mark.django_db
def test_export_is_exactly_the_filtered_table(people):
    c = api(people["admin"])
    q = f"?county={people['mombasa'].pk}&status=active"
    listed = c.get(f"/api/v1/participants{q}").json()
    resp = c.post(URL + q, BODY, content_type="application/json")
    assert resp.status_code == 200 and "attachment" in resp["Content-Disposition"]
    rows = parse(resp)
    head = rows[0]
    # With no choice made, the file holds every field, starting with the ones the table shows.
    assert head[:2] == ["Name", "Given name"] and {"Gender", "Age", "Project", "Cohort"} <= set(
        head
    )
    col = head.index
    assert [r[0].lstrip("'") for r in rows[1:]] == [r["name"] for r in listed["results"]]
    assert len(rows) - 1 == listed["total"] == 2
    assert {r[col("County")] for r in rows[1:]} == {people["mombasa"].name}
    assert {r[col("Status")] for r in rows[1:]} == {"Active"}
    assert resp["X-Export-Rows"] == "2"


@pytest.mark.django_db
def test_formula_like_names_are_escaped_and_excel_has_an_about_sheet(people):
    c = api(people["admin"])
    rows = parse(c.post(URL, BODY, content_type="application/json"))
    assert "'=HYPERLINK(1)" in [r[0] for r in rows]
    resp = c.post(URL, {**BODY, "format": "xlsx"}, content_type="application/json")
    wb = load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["Data", "About"]
    about = dict(wb["About"].iter_rows(min_row=2, values_only=True))
    assert about["Purpose"] == BODY["purpose"] and about["Rows"] == 4


@pytest.mark.django_db
def test_scope_is_respected(people, make_user):
    officer = make_user("off", "Placement officer")
    scope(officer, "project", people["world"]["progs"][1].pk)
    grant(people["admin"], officer)
    rows = parse(api(officer).post(URL, BODY, content_type="application/json"))
    assert [r[0] for r in rows[1:]] == ["'=HYPERLINK(1)"]


@pytest.mark.django_db
def test_needs_the_grant_a_purpose_and_rows(people, make_user):
    other = make_user("other", "Data steward")
    assert api(other).post(URL, BODY, content_type="application/json").status_code == 403
    g = grant(people["admin"], other)
    c = api(other)
    ok = c.post(URL, BODY, content_type="application/json")
    assert ok.status_code in (200, 409)  # allowed; 409 only if scope shows no rows
    no_purpose = api(people["admin"]).post(
        URL, {"format": "csv", "purpose": " "}, content_type="application/json"
    )
    assert no_purpose.status_code == 409 and no_purpose.json()["errors"][0]["field"] == "purpose"
    empty = api(people["admin"]).post(URL + "?q=zzzzzzqqq", BODY, content_type="application/json")
    assert empty.status_code == 409 and empty.json()["errors"][0]["code"] == "empty"
    bad = api(people["admin"]).post(URL + "?county=nope", BODY, content_type="application/json")
    assert bad.status_code == 409
    pdf = api(people["admin"]).post(
        URL, {"format": "pdf", "purpose": "x"}, content_type="application/json"
    )
    assert pdf.status_code == 409
    # Withdrawn or expired grants stop it at once.
    identity.revoke_grant(actor=people["admin"], grant=g, reason="done")
    assert api(other).post(URL, BODY, content_type="application/json").status_code == 403


@pytest.mark.django_db
def test_logged_and_audited_without_row_data_and_not_stored(people):
    api(people["admin"]).post(
        URL + f"?county={people['mombasa'].pk}", BODY, content_type="application/json"
    )
    log = ExportLog.objects.get(dataset="youth")
    assert log.row_count == 3 and log.content is None and log.expires_at is None
    assert log.detail["purpose"] == BODY["purpose"]
    ev = AuditEvent.objects.get(action="export.created")
    text = str(ev.after) + ev.reason
    assert "Amina" not in text and "Baraka" not in text
    assert ev.reason == BODY["purpose"] and ev.after["identifiable"] is True


@pytest.mark.django_db
def test_old_export_page_does_not_list_table_exports(people, make_user):
    api(people["admin"]).post(URL, BODY, content_type="application/json")
    analyst = make_user("mne", "M&E analyst")
    ExportLog.objects.update(actor=analyst)
    resp = api(analyst).get("/api/v1/exports")
    assert resp.status_code == 200 and resp.json()["log"] == []


@pytest.mark.django_db
def test_grants_api(people, make_user):
    admin, target = people["admin"], make_user("t", "Data steward")
    c = api(admin)
    out = c.get("/api/v1/identity/grants").json()
    assert {g["code"] for g in out["grantable"]} >= {"exports.identifiable"}
    exp = (timezone.localdate() + timedelta(days=5)).isoformat()
    body = {
        "user_id": target.pk,
        "permission": "exports.identifiable",
        "purpose": "Quarterly list",
        "expires_on": exp,
    }
    made = c.post("/api/v1/identity/grants", body, content_type="application/json")
    assert made.status_code == 201 and made.json()["state"] == "active"
    far = {**body, "expires_on": (timezone.localdate() + timedelta(days=400)).isoformat()}
    assert (
        c.post("/api/v1/identity/grants", far, content_type="application/json").status_code == 400
    )
    role_perm = {**body, "permission": "audit.view"}
    assert (
        c.post("/api/v1/identity/grants", role_perm, content_type="application/json").status_code
        == 400
    )
    gid = made.json()["id"]
    assert (
        c.post(
            f"/api/v1/identity/grants/{gid}/revoke", {}, content_type="application/json"
        ).status_code
        == 400
    )
    rev = c.post(
        f"/api/v1/identity/grants/{gid}/revoke", {"reason": "Done"}, content_type="application/json"
    )
    assert rev.status_code == 200 and rev.json()["state"] == "revoked"
    assert api(target).get("/api/v1/identity/grants").status_code == 403
