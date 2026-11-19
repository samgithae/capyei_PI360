"""De-identified exports (T-071): no direct identifier can appear, small groups are hidden,
every export and download is logged, files expire, and only permitted people can export."""

import csv
import io
import re
from datetime import date, timedelta

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from openpyxl import load_workbook

from apps.audit.models import AuditEvent
from apps.configuration.models import County
from apps.participants.models import Participant
from apps.participants.models import ParticipantContact as Contact
from apps.reporting import exports
from apps.reporting.models import ExportLog

URL = "/api/v1/exports"
NAMES = ["Wanjiru Kamau", "Otieno Odhiambo", "Aisha Mohamed", "Grace Njeri", "Peter Mwangi"]
PHONES = ["0712345601", "0712345602", "0712345603"]


def api(user):
    c = Client()
    c.force_login(user)
    return c


def person(name, county, gender="female", age=20, phone=None, email=None):
    p = Participant.objects.create(
        full_name_source=name,
        given_name=name.split()[0],
        family_name=name.split()[-1],
        gender=gender,
        date_of_birth=date.today().replace(year=date.today().year - age) - timedelta(days=30),
        origin_county=County.objects.get(code=county),
    )
    if phone:
        Contact.objects.create(participant=p, kind="phone", value=phone)
    if email:
        Contact.objects.create(participant=p, kind="email", value=email)
    return p


@pytest.fixture
def world(db):
    # 6 young women from county 01 (a big group), 3 from county 02, 1 older man (all too few).
    for i in range(6):
        person(f"Wanjiru Kamau{i}", "01", phone=PHONES[i % 3], email=f"w{i}@example.org")
    for i in range(3):
        person(f"Aisha Mohamed{i}", "02")
    person("Peter Mwangi", "02", gender="male", age=33, phone="0799000111")


@pytest.fixture
def analyst(make_user):
    return make_user("mne", "M&E analyst")


def rows_of(log):
    return list(csv.reader(io.StringIO(bytes(log.content).decode("utf-8-sig"))))


@pytest.mark.django_db
def test_records_export_has_only_allowed_columns_and_no_identifier(world, analyst):
    log = exports.create(actor=analyst, dataset="youth_records", file_format="csv")
    rows = rows_of(log)
    assert rows[0] == [h for _k, h, _m in exports.FIELDS["youth_records"]]
    blob = bytes(log.content).decode("utf-8-sig")
    for needle in [*NAMES, *PHONES, "0799000111", "@example.org", "Kamau", "Mohamed", "Mwangi"]:
        assert needle not in blob
    assert not re.search(r"\d{4}-\d{2}-\d{2}", blob)  # no dates, so no date of birth
    assert all(re.fullmatch(r"Y-[0-9A-F]{8}", r[0]) for r in rows[1:])
    assert len({r[0] for r in rows[1:]}) == len(rows) - 1


@pytest.mark.django_db
def test_small_groups_are_generalised_then_withheld(world, analyst):
    log = exports.create(actor=analyst, dataset="youth_records", file_format="csv")
    body = rows_of(log)[1:]
    assert len(body) == 6 and log.row_count == 6 and log.withheld_rows == 4
    assert {r[3] for r in body} == {County.objects.get(code="01").name}
    assert {r[1] for r in body} == {"Female"} and {r[2] for r in body} == {"18 to 24"}


@pytest.mark.django_db
def test_summary_hides_small_counts_and_a_second_cell(world, analyst):
    log = exports.create(actor=analyst, dataset="summary", file_format="csv")
    rows = {(r[0], r[1]): r for r in rows_of(log)[1:]}
    assert rows[("Gender", "Male")][2] == "< 5"  # one youth
    # Hiding only that count would let it be worked out from the total, so the other is hidden.
    assert rows[("Gender", "Female")][2] == "Hidden"
    assert rows[("Age band", "18 to 24")][2] == "Hidden"
    county01 = County.objects.get(code="01").name
    assert rows[("County", county01)][2] == "Hidden"  # 6 youth, hidden beside the small county
    assert rows[("Age band", "30 and over")][2] == "< 5"
    assert log.suppressed_cells >= 2
    assert log.row_count == len(rows)


@pytest.mark.django_db
def test_excel_has_definitions_and_the_rules_applied(world, analyst):
    log = exports.create(actor=analyst, dataset="youth_records", file_format="xlsx")
    wb = load_workbook(io.BytesIO(bytes(log.content)))
    assert wb.sheetnames == ["Data", "Definitions"]
    text = " ".join(str(c.value) for row in wb["Definitions"].iter_rows() for c in row)
    assert "Smallest group shown" in text and "De-identified" in text and "D-045" in text
    assert "Kamau" not in text


@pytest.mark.django_db
def test_two_exports_cannot_be_joined(world, analyst):
    def refs():
        log = exports.create(actor=analyst, dataset="youth_records", file_format="csv")
        return {r[0] for r in rows_of(log)[1:]}

    a, b = refs(), refs()
    assert not a & b


@pytest.mark.django_db
def test_every_export_and_download_is_logged(world, analyst):
    c = api(analyst)
    made = c.post(URL, {"dataset": "summary", "format": "csv"}, content_type="application/json")
    assert made.status_code == 201
    eid = made.json()["id"]
    assert AuditEvent.objects.filter(action="export.created", object_id=eid).count() == 1
    dl = c.get(f"{URL}/{eid}/download")
    assert dl.status_code == 200 and dl["Content-Disposition"].startswith("attachment")
    assert dl["Cache-Control"] == "no-store"
    assert AuditEvent.objects.filter(action="export.downloaded", object_id=eid).count() == 1
    ev = AuditEvent.objects.get(action="export.created")
    assert "Wanjiru" not in str(ev.after)  # counts only
    assert ExportLog.objects.get(pk=eid).downloads == 1
    assert c.get(URL).json()["log"][0]["id"] == eid


@pytest.mark.django_db
def test_only_the_maker_can_download_and_only_permitted_roles_export(world, analyst, make_user):
    eid = exports.create(actor=analyst, dataset="summary", file_format="csv").id
    other = make_user("mne2", "M&E analyst")
    assert api(other).get(f"{URL}/{eid}/download").status_code == 404
    for role in ("Placement officer", "Data steward"):
        u = make_user(role.split()[0].lower(), role)
        body = {"dataset": "summary", "format": "csv"}
        assert api(u).post(URL, body, content_type="application/json").status_code == 403
    admin = make_user("admin9", "Administrator")  # holds every analyst permission (migration 0009)
    assert api(admin).get(URL).status_code == 200
    assert Client().post(URL, {}, content_type="application/json").status_code in (401, 403)


@pytest.mark.django_db
def test_expired_files_are_refused_and_purged(world, analyst, capsys):
    log = exports.create(actor=analyst, dataset="summary", file_format="csv")
    assert log.expires_at - log.created_at >= timedelta(days=6)
    ExportLog.objects.update(expires_at=timezone.now() - timedelta(hours=1))
    r = api(analyst).get(f"{URL}/{log.id}/download")
    assert r.status_code == 410 and r.json()["errors"][0]["code"] == "expired"
    call_command("purge_exports")
    assert "Deleted 1" in capsys.readouterr().out
    log.refresh_from_db()
    assert log.content is None and log.purged_at
    assert AuditEvent.objects.filter(action="export.purged").count() == 1
    assert exports.purge_expired() == 0  # the log row stays; nothing more to delete


@pytest.mark.django_db
def test_bad_requests_and_settings(world, analyst, make_user):
    c = api(analyst)
    bad = c.post(URL, {"dataset": "everything", "format": "csv"}, content_type="application/json")
    assert bad.status_code == 409 and bad.json()["errors"][0]["field"] == "dataset"
    bad = c.post(URL, {"dataset": "summary", "format": "pdf"}, content_type="application/json")
    assert bad.status_code == 409 and bad.json()["errors"][0]["field"] == "format"
    # The threshold is an administrator setting and cannot go below its floor.
    from apps.intelligence import services as intelligence

    admin = make_user("admin1", "Administrator")
    with pytest.raises(intelligence.RuleViolation):
        intelligence.update_settings(actor=admin, values={"exports.small_cell": 1})
    intelligence.update_settings(actor=admin, values={"exports.small_cell": 8})
    assert c.get(URL).json()["rules"]["small_cell"] == 8
    log = exports.create(actor=analyst, dataset="youth_records", file_format="csv")
    # No county reaches 8, so the county is hidden; the nine young women together do.
    assert log.small_cell_threshold == 8 and log.row_count == 9
    assert {r[3] for r in rows_of(log)[1:]} == {exports.NOT_SHOWN}
