"""Choosing the fields of a youth export. By default every field is exported, including the ones
reached through relationships, one row per youth with related records joined in one cell. A choice
narrows the columns; an unknown field is refused; the log holds the chosen keys but no values."""

import csv
import io
from datetime import date, timedelta

import pytest
from django.test import Client
from django.utils import timezone
from openpyxl import load_workbook

from apps.audit.models import AuditEvent
from apps.configuration.models import County, QualificationGrade, QualificationLevel, Sector, Skill
from apps.identity import services as identity
from apps.participants.models import (
    ParticipantCertification,
    ParticipantContact,
    ParticipantExperience,
    ParticipantLanguage,
    ParticipantPractical,
    ParticipantQualification,
    ParticipantReadiness,
    ParticipantResidence,
    ParticipantSkill,
    SourceIdentifier,
)
from apps.reporting import exports
from apps.reporting.models import ExportLog

from .test_followups import client_for, enrollment, officer, place, youth  # noqa: F401
from .test_participants import world  # noqa: F401
from .test_referrals import JSON, refer
from .test_table_exports_more import Employer, Opportunity

URL = "/api/v1/exports/table/youth"
BODY = {"format": "csv", "purpose": "Mombasa follow-up calls"}


def parse(resp):
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


def as_dicts(resp):
    head, *rows = parse(resp)
    return [dict(zip(head, r, strict=True)) for r in rows]


def post(user, query="", **body):
    c = Client()
    c.force_login(user)
    return c.post(URL + query, {**BODY, **body}, content_type=JSON)


@pytest.fixture
def admin(make_user):
    user = make_user("adm", "Administrator")
    identity.grant_permission(
        actor=user,
        user=user,
        permission="exports.identifiable",
        purpose="Programme reporting",
        expires_at=timezone.now() + timedelta(days=3),
    )
    return user


@pytest.fixture
def full(youth, enrollment, officer, admin):  # noqa: F811
    """One youth with something in every related table, a referral and a placement."""
    mombasa = County.objects.get(code="01")
    youth.given_name, youth.family_name, youth.gender = "Test", "Youth", "female"
    youth.date_of_birth, youth.origin_county, youth.status = date(2006, 3, 4), mombasa, "active"
    youth.save()
    ParticipantContact.objects.create(
        participant=youth, kind="phone", value="0712345678", is_primary=True
    )
    ParticipantContact.objects.create(participant=youth, kind="phone", value="0722000111")
    ParticipantContact.objects.create(participant=youth, kind="email", value="a@example.org")
    ParticipantResidence.objects.create(
        participant=youth, county=mombasa, sub_county_source="Nyali", ward_source="Frere Town"
    )
    SourceIdentifier.objects.create(participant=youth, source="TVET", identifier="T-77")
    level = QualificationLevel.objects.filter(name="Diploma").first() or (
        QualificationLevel.objects.create(code="DIP", name="Diploma", rank=40)
    )
    grade = QualificationGrade.objects.create(
        code="TX-CR", name="Test credit", level=level, rank=99
    )
    ParticipantQualification.objects.create(
        participant=youth, level=level, title="Food Production", institution="Mombasa TTI",
        year_awarded=2024, grade=grade,
    )  # fmt: skip
    ParticipantCertification.objects.create(
        participant=youth, name="First aid", issuer="Red Cross", year_obtained=2023
    )
    ParticipantLanguage.objects.create(participant=youth, language="Swahili", proficiency="native")
    welding = Skill.objects.create(code="TX-WLD", name="Test welding")
    ParticipantSkill.objects.create(participant=youth, skill=welding, proficiency=3)
    ParticipantSkill.objects.create(
        participant=youth, skill=Skill.objects.create(code="TX-CK", name="Test cooking")
    )
    ParticipantExperience.objects.create(
        participant=youth, role_title="Cook", employer_name="Hotel X", months=6
    )
    ParticipantExperience.objects.create(participant=youth, role_title="Helper", months=3)
    ParticipantPractical.objects.create(
        participant=youth, organisation="Kitchen Co", kind="internship", role="Intern"
    )
    ready = ParticipantReadiness.objects.create(
        participant=youth, available_from=date(2026, 12, 1), work_patterns=["full_time", "remote"],
        preferred_roles=["Chef"], willing_to_relocate=True, summary="Keen cook.",
    )  # fmt: skip
    ready.interest_sectors.add(Sector.objects.create(code="TX-HOS", name="Test hospitality"))
    ready.preferred_counties.add(mombasa)
    acme = Employer.objects.create(name="Acme Traders")
    opp = Opportunity.objects.create(
        employer=acme, title="Sales assistant", status=Opportunity.OPEN,
        closing_date=date.today() + timedelta(days=30), positions=3,
    )  # fmt: skip
    oc = client_for(officer)
    assert refer(oc, youth, opp).status_code == 201
    place(oc, youth)
    return youth


@pytest.mark.django_db
def test_every_field_is_exported_by_default_including_related_ones(admin, full):
    resp = post(admin)
    assert resp.status_code == 200
    [row] = as_dicts(resp)
    keys = {f["label"] for g in exports.youth_groups() for f in g["fields"]}
    assert set(row) == keys  # no field is missing and none is extra
    assert (
        row["Name"] == "Test Youth A" and row["Gender"] == "Female" and row["County"] == "Mombasa"
    )
    assert row["Date of birth"] == "2006-03-04" and row["Status"] == "Active"
    assert row["Phone"] == "0712345678; 0722000111"  # the primary number first
    assert row["Email"] == "a@example.org"
    assert (row["Residence county"], row["Sub-county"], row["Ward"]) == (
        "Mombasa",
        "Nyali",
        "Frere Town",
    )
    assert row["Source IDs"] == "TVET: T-77"
    assert row["Assigned officer"] == "wanjiru"
    assert row["Programme"] and row["Cohort"] and row["Course"] and row["Training institution"]
    assert (
        row["Highest qualification"] == "Diploma: Food Production (Mombasa TTI, 2024, Test credit)"
    )
    assert row["Certifications"] == "First aid (Red Cross, 2023)"
    assert row["Languages"] == "Swahili (Native or bilingual)"
    assert row["Skills"] == "Test cooking (Working); Test welding (Advanced)"
    assert row["Work experience"] == "Cook, Hotel X (6 months); Helper (3 months)"
    assert row["Months of work experience"] == "9"
    assert row["Internships, attachments and volunteering"] == "Internship: Kitchen Co (Intern)"
    assert (
        row["Available from"] == "2026-12-01"
        and row["Work patterns"] == "Full time; Remote or home based"
    )
    assert (
        row["Sectors of interest"] == "Test hospitality" and row["Preferred counties"] == "Mombasa"
    )
    assert row["Preferred roles"] == "Chef" and row["Willing to relocate"] == "Yes"
    assert row["Introduction"] == "Keen cook."
    assert row["Referrals"].startswith("Sales assistant at Acme Traders: ")
    assert "current" in row["Placements"] and "Wage employment" in row["Placements"]


@pytest.mark.django_db
def test_a_choice_narrows_the_columns_and_keeps_catalogue_order(admin, full):
    resp = post(admin, fields=["status", "name", "phone"])
    assert parse(resp)[0] == ["Name", "Status", "Phone"]
    assert parse(resp)[1][2] == "0712345678; 0722000111"
    xlsx = post(admin, format="xlsx", fields=["name", "skills"])
    wb = load_workbook(io.BytesIO(xlsx.content))
    assert [c.value for c in wb["Data"][1]] == ["Name", "Skills"]
    about = dict(wb["About"].iter_rows(min_row=2, values_only=True))
    assert about["Fields"] == "Name, Skills"


@pytest.mark.django_db
def test_one_row_per_youth_however_many_related_records(admin, full, make_user):  # noqa: F811
    rows = as_dicts(post(admin, fields=["name", "skills", "work_experience", "programme"]))
    assert len(rows) == 1


@pytest.mark.django_db
def test_unknown_or_empty_choices_are_refused(admin, full):
    bad = post(admin, fields=["name", "national_id"])
    assert bad.status_code == 409
    err = bad.json()["errors"][0]
    assert err["field"] == "fields" and err["code"] == "invalid" and "national_id" in err["message"]
    empty = post(admin, fields=[])
    assert empty.status_code == 409 and empty.json()["errors"][0]["code"] == "required"
    other = Client()
    other.force_login(admin)
    resp = other.post(
        "/api/v1/exports/table/employers", {**BODY, "fields": ["name"]}, content_type=JSON
    )
    assert resp.status_code == 409 and resp.json()["errors"][0]["code"] == "invalid"
    assert ExportLog.objects.count() == 0  # nothing was exported or logged


@pytest.mark.django_db
def test_referrals_and_placements_respect_record_scope(admin, full, make_user):  # noqa: F811
    # A user who may see the youth but not their referrals/placements would get blank cells; here
    # the check is the simpler one: an officer with no scope over this youth gets no row at all.
    stranger = make_user("stranger", "Placement officer")
    identity.set_scopes(actor=None, user=stranger, scopes=[("officer", "self")])
    identity.grant_permission(
        actor=admin, user=stranger, permission="exports.identifiable", purpose="Reporting",
        expires_at=timezone.now() + timedelta(days=3),
    )  # fmt: skip
    resp = post(stranger)
    assert resp.status_code == 409 and resp.json()["errors"][0]["code"] == "empty"


@pytest.mark.django_db
def test_the_log_and_audit_hold_the_chosen_keys_but_no_values(admin, full):
    post(admin, fields=["name", "phone", "email"])
    log = ExportLog.objects.get(dataset="youth")
    assert log.detail["fields"] == ["name", "phone", "email"]
    assert log.detail["columns"] == ["Name", "Phone", "Email"]
    ev = AuditEvent.objects.get(action="export.created")
    assert ev.after["fields"] == ["name", "phone", "email"]
    text = str(ev.after) + ev.reason + str(log.detail)
    for value in ("Test Youth A", "0712345678", "a@example.org"):
        assert value not in text


@pytest.mark.django_db
def test_default_log_records_every_field(admin, full):
    post(admin)
    ev = AuditEvent.objects.get(action="export.created")
    every = [f["key"] for g in exports.youth_groups() for f in g["fields"]]
    assert ev.after["fields"] == every


@pytest.mark.django_db
def test_field_list_endpoint_is_grouped_and_flags_sensitive_fields(admin, full, make_user):  # noqa: F811
    c = Client()
    c.force_login(admin)
    resp = c.get("/api/v1/exports/fields/youth")
    assert resp.status_code == 200
    groups = {g["key"]: g for g in resp.json()["groups"]}
    assert {"identity", "contact", "residence", "enrolment", "education", "skills", "work",
            "readiness", "outcomes"} <= set(groups)  # fmt: skip
    sensitive = {f["key"] for g in groups.values() for f in g["fields"] if f["sensitive"]}
    assert {"phone", "email", "date_of_birth", "ward"} <= sensitive and "name" not in sensitive
    assert c.get("/api/v1/exports/fields/employers").status_code == 404
    nobody = make_user("nobody", "Data steward")
    c.force_login(nobody)
    assert c.get("/api/v1/exports/fields/youth").status_code == 403
