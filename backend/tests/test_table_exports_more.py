"""Export from the other tables (employers, opportunities, referrals, placements, follow-ups).

Each file is the list as filtered on screen. The companies' tables hold no names of young people,
the others hold names; all respect record scope and are logged without row data."""

import csv
import io
from datetime import date, timedelta

import pytest
from django.test import Client
from django.utils import timezone
from openpyxl import load_workbook

from apps.audit.models import AuditEvent
from apps.employers.models import Employer, Opportunity
from apps.identity import services as identity
from apps.participants.models import Participant
from apps.reporting.models import ExportLog

from .test_followups import client_for, enrollment, officer, place, youth  # noqa: F401
from .test_participants import enrol, world  # noqa: F401
from .test_referrals import JSON, refer

BODY = {"format": "csv", "purpose": "Quarterly review"}


def url(table):
    return f"/api/v1/exports/table/{table}"


def parse(resp):
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


def grant(admin, user):
    return identity.grant_permission(
        actor=admin,
        user=user,
        permission="exports.identifiable",
        purpose="Programme reporting",
        expires_at=timezone.now() + timedelta(days=3),
    )


@pytest.fixture
def admin(make_user):
    user = make_user("adm", "Administrator")
    grant(user, user)
    return user


@pytest.fixture
def data(admin, officer, youth, enrollment, world):  # noqa: F811
    """Two companies, two opportunities, a referral, a placement and its follow-ups."""
    acme = Employer.objects.create(name="Acme Traders")
    farm = Employer.objects.create(name="Farm Two")
    open_opp = Opportunity.objects.create(
        employer=acme, title="Sales assistant", status=Opportunity.OPEN,
        closing_date=date.today() + timedelta(days=30), positions=3,
    )  # fmt: skip
    Opportunity.objects.create(employer=farm, title="Picker", status=Opportunity.DRAFT)
    oc = client_for(officer)
    assert refer(oc, youth, open_opp).status_code == 201
    place(oc, youth)
    other = Participant.objects.create(full_name_source="Test Youth Elsewhere")
    return {"acme": acme, "farm": farm, "opp": open_opp, "other": other, "oc": oc}


def export(user, table, query="", **body):
    c = Client()
    c.force_login(user)
    return c.post(url(table) + query, {**BODY, **body}, content_type=JSON)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "table,list_url,query,head,expected",
    [
        ("employers", "/api/v1/employers", "?q=acme", "Employer", 1),
        ("opportunities", "/api/v1/opportunities", "?status=open", "Opportunity", 1),
        ("referrals", "/api/v1/referrals", "?stage=active", "Youth", 1),
        ("placements", "/api/v1/placements", "?pathway=wage", "Youth", 1),
        ("followups", "/api/v1/followups", "?state=open", "Youth", 5),
    ],
)
def test_each_export_is_exactly_the_filtered_table(
    admin, data, table, list_url, query, head, expected
):
    c = Client()
    c.force_login(admin)
    listed = c.get(list_url + query).json()
    resp = export(admin, table, query)
    assert resp.status_code == 200 and "attachment" in resp["Content-Disposition"]
    rows = parse(resp)
    assert rows[0][0] == head
    assert len(rows) - 1 == listed["total"] == expected
    assert resp["X-Export-Rows"] == str(expected)
    # A filter that leaves nothing is refused rather than giving an empty file.
    miss = export(admin, table, "?q=zzzzqqqq")
    assert miss.status_code == 409 and miss.json()["errors"][0]["code"] == "empty"


@pytest.mark.django_db
def test_filters_narrow_the_file(admin, data):
    assert len(parse(export(admin, "employers"))) - 1 == 2
    assert len(parse(export(admin, "opportunities"))) - 1 == 2
    only_open = parse(export(admin, "opportunities", "?status=open"))
    assert [r[0] for r in only_open[1:]] == ["Sales assistant"]
    assert (
        only_open[1][1] == "Acme Traders"
        and only_open[1][only_open[0].index("Closing date")] == data["opp"].closing_date.isoformat()
    )


@pytest.mark.django_db
def test_company_tables_have_no_youth_names_and_say_so(admin, data):
    for table in ("employers", "opportunities"):
        text = export(admin, table).content.decode("utf-8-sig")
        assert "Test Youth" not in text
        wb = load_workbook(io.BytesIO(export(admin, table, format="xlsx").content))
        about = dict(wb["About"].iter_rows(min_row=2, values_only=True))
        assert "no names" in about["Handling"]
    people = load_workbook(io.BytesIO(export(admin, "referrals", format="xlsx").content))
    assert (
        "Contains names" in dict(people["About"].iter_rows(min_row=2, values_only=True))["Handling"]
    )


@pytest.mark.django_db
def test_people_tables_respect_record_scope(admin, officer, data, make_user):  # noqa: F811
    # The admin sees the unassigned youth too; make a referral for them to prove the scope.
    Participant.objects.filter(pk=data["other"].pk).update(assigned_officer=None)
    grant(admin, officer)
    rows = parse(export(officer, "referrals"))
    assert [r[0] for r in rows[1:]] == ["Test Youth A"]
    assert {r[0] for r in parse(export(officer, "placements"))[1:]} == {"Test Youth A"}
    assert {r[0] for r in parse(export(officer, "followups"))[1:]} == {"Test Youth A"}


@pytest.mark.django_db
def test_each_table_needs_the_grant(data, officer):  # noqa: F811
    for table in ("employers", "opportunities", "referrals", "placements", "followups"):
        assert export(officer, table).status_code == 403


@pytest.mark.django_db
def test_bad_filters_and_unknown_tables_are_refused(admin, data):
    assert export(admin, "employers", "?sector=nope").status_code == 409
    assert export(admin, "placements", "?employer=nope").status_code == 409
    assert export(admin, "referrals", "?participant=nope").status_code == 409
    assert export(admin, "nothing").status_code == 404


@pytest.mark.django_db
def test_logged_per_table_without_names(admin, data):
    export(admin, "referrals", "?stage=active")
    export(admin, "employers", "?q=acme")
    assert set(ExportLog.objects.values_list("dataset", flat=True)) == {"referrals", "employers"}
    log = ExportLog.objects.get(dataset="referrals")
    assert log.detail["filters"] == {"stage": "active"} and log.content is None
    text = " ".join(
        str(e.after) + e.reason for e in AuditEvent.objects.filter(action="export.created")
    )
    assert "Test Youth" not in text and "Acme" not in text


@pytest.mark.django_db
def test_a_formula_in_a_company_name_is_escaped(admin, data):
    Employer.objects.create(name="=HYPERLINK(1)")
    assert "'=HYPERLINK(1)" in [r[0] for r in parse(export(admin, "employers"))]


# --- the field picker on every table -------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "table", ["employers", "opportunities", "referrals", "placements", "followups"]
)
def test_every_table_lists_its_fields_and_exports_all_by_default(admin, data, table):
    c = Client()
    c.force_login(admin)
    groups = c.get(f"/api/v1/exports/fields/{table}").json()["groups"]
    headings = [f["label"] for g in groups for f in g["fields"]]
    assert len(headings) == len(set(headings)) and len(headings) >= 7
    rows = parse(export(admin, table))
    assert rows[0] == headings  # nothing chosen = every field, in the picker's order
    log = ExportLog.objects.get(dataset=table)
    assert log.detail["fields"] == [f["key"] for g in groups for f in g["fields"]]


@pytest.mark.django_db
def test_a_choice_narrows_the_columns_and_keeps_catalogue_order(admin, data):
    resp = export(admin, "referrals", fields=["stage", "youth"])
    rows = parse(resp)
    assert rows[0] == ["Youth", "Stage"] and rows[1][0] == "Test Youth A"
    log = ExportLog.objects.get(dataset="referrals")
    assert log.detail["fields"] == ["youth", "stage"]
    audit = AuditEvent.objects.get(action="export.created")
    assert audit.after["fields"] == ["youth", "stage"] and "Test Youth A" not in str(audit.after)


@pytest.mark.django_db
def test_unknown_or_empty_choices_are_refused_on_every_table(admin, data):
    for table in ("employers", "opportunities", "referrals", "placements", "followups"):
        bad = export(admin, table, fields=["nope"])
        assert bad.status_code == 409 and bad.json()["errors"][0]["code"] == "invalid"
        none = export(admin, table, fields=[])
        assert none.status_code == 409 and none.json()["errors"][0]["code"] == "required"
    assert ExportLog.objects.count() == 0


@pytest.mark.django_db
def test_employer_contacts_are_sensitive_and_joined_in_one_cell(admin, data):
    from apps.employers.models import EmployerContact

    EmployerContact.objects.create(
        employer=data["acme"], name="Amina Hassan", role="HR", email="amina@acme.test",
        phone="0700111222", is_primary=True,
    )  # fmt: skip
    EmployerContact.objects.create(employer=data["acme"], name="Bob Otieno")
    c = Client()
    c.force_login(admin)
    groups = c.get("/api/v1/exports/fields/employers").json()["groups"]
    flagged = {f["key"] for g in groups for f in g["fields"] if f["sensitive"]}
    assert flagged == {"contacts"}
    rows = parse(export(admin, "employers", fields=["name", "contacts", "open_opportunities"]))
    acme = next(r for r in rows[1:] if r[0] == "Acme Traders")
    # Columns follow the picker's order, not the order they were asked for.
    assert acme[1] == "1"
    assert acme[2] == "Amina Hassan (HR), amina@acme.test, 0700111222; Bob Otieno"
    # Leave contacts out and they are not in the file or the log.
    rows = parse(export(admin, "employers", fields=["name"]))
    assert rows[0] == ["Employer"] and "Amina" not in str(rows)
