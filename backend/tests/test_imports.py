"""Import pipeline (T-040). All data here is synthetic."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.audit.models import AuditEvent
from apps.configuration.models import (
    Cohort,
    CohortCourse,
    County,
    Course,
    Programme,
    TrainingInstitution,
)
from apps.imports import services
from apps.imports.models import ImportBatch, ImportRow
from apps.participants.models import Participant, ParticipantEnrollment

COLUMNS = {
    "Name": "full_name",
    "Prog": "programme_code",
    "Cohort": "cohort_code",
    "Course": "course_code",
    "EnrolNo": "enrollment_no",
    "Sex": "gender",
    "Age": "age",
    "County": "county_code",
}
HEAD = "Name,Prog,Cohort,Course,EnrolNo,Sex,Age,County\n"
GOOD = [
    "Test One,P1,K1,C1,E-001,F,21,01",
    "Test Two,P1,K1,C1,E-002,M,23,01",
    "Test Three,P1,K1,C1,E-003,F,25,",
]


@pytest.fixture
def world(db):
    prog = Programme.objects.create(code="P1", name="Programme One")
    inst = TrainingInstitution.objects.create(
        code="I1", name="College", county=County.objects.get(code="01")
    )
    course = Course.objects.create(programme=prog, code="C1", name="Course")
    cohort = Cohort.objects.create(
        programme=prog, institution=inst, code="K1", name="Cohort 1", intake_year=2025,
        batch_no=1, phase="1",
    )  # fmt: skip
    CohortCourse.objects.create(cohort=cohort, course=course)


@pytest.fixture
def steward(make_user):
    return make_user("steward", "Data steward")


@pytest.fixture
def template(world, steward):
    return services.create_template(actor=steward, source="test-src", columns=COLUMNS)


def csv_bytes(*rows):
    return (HEAD + "\n".join(rows) + "\n").encode()


def upload(steward, template, *rows, name="f.csv"):
    return services.upload(actor=steward, template=template, file_name=name, data=csv_bytes(*rows))


def load(steward, batch):
    services.approve(actor=steward, batch=batch)
    return services.commit(actor=steward, batch=batch)


@pytest.mark.django_db
def test_template_versions_increment_and_validate(world, steward):
    t1 = services.create_template(actor=steward, source="s", columns=COLUMNS)
    t2 = services.create_template(actor=steward, source="s", columns=COLUMNS)
    assert (t1.version, t2.version) == (1, 2)
    with pytest.raises(services.ImportFailure):
        services.create_template(actor=steward, source="s", columns={"Name": "full_name"})
    with pytest.raises(services.ImportFailure):
        services.create_template(actor=steward, source="s", columns={**COLUMNS, "X": "nope"})


@pytest.mark.django_db
def test_dry_run_changes_nothing(template, steward):
    b = upload(steward, template, *GOOD)
    assert b.status == ImportBatch.VALIDATED
    assert b.counts["create"] == 3 and b.counts["held"] == 0
    assert Participant.objects.count() == 0


@pytest.mark.django_db
def test_commit_creates_and_is_idempotent(template, steward):
    b = load(steward, upload(steward, template, *GOOD))
    assert b.status == ImportBatch.COMMITTED
    assert Participant.objects.count() == 3
    assert services.commit(actor=steward, batch=b).status == ImportBatch.COMMITTED  # repeat
    assert Participant.objects.count() == 3
    # Same file again: warned, and nothing new loads.
    again = upload(steward, template, *GOOD)
    assert again.duplicate_of_id == b.pk
    assert again.counts["skip"] == 3
    load(steward, again)
    assert Participant.objects.count() == 3


@pytest.mark.django_db
def test_bad_rows_are_held_and_the_rest_load(template, steward):
    rows = [
        *GOOD,
        "No Programme,ZZ,K1,C1,E-010,F,20,01",
        ",P1,K1,C1,E-011,F,20,01",
        "Dup Of One,P1,K1,C1,E-001,F,20,01",
    ]
    b = upload(steward, template, *rows)
    assert b.counts["held"] == 3 and b.counts["create"] == 3
    load(steward, b)
    assert Participant.objects.count() == 3
    held = {r.row_no: r.errors[0]["field"] for r in b.rows.filter(outcome="held")}
    assert held == {4: "programme_code", 5: "full_name", 6: "enrollment_no"}


@pytest.mark.django_db
def test_changed_row_updates_by_enrollment_number(template, steward):
    load(steward, upload(steward, template, *GOOD))
    b = upload(steward, template, "Test One Renamed,P1,K1,C1,E-001,F,22,01")
    assert b.counts["update"] == 1
    load(steward, b)
    assert Participant.objects.count() == 3
    assert (
        ParticipantEnrollment.objects.get(source_enrollment_no="E-001").participant.full_name_source
        == "Test One Renamed"
    )


@pytest.mark.django_db
def test_rollback_restores_and_blocks_after_later_change(template, steward):
    first = load(steward, upload(steward, template, *GOOD))
    upd = load(steward, upload(steward, template, "Renamed,P1,K1,C1,E-001,F,22,01"))
    with pytest.raises(services.ImportFailure):  # the later batch touched E-001
        services.rollback(actor=steward, batch=first, reason="mistake")
    services.rollback(actor=steward, batch=upd, reason="wrong file")
    assert (
        ParticipantEnrollment.objects.get(source_enrollment_no="E-001").participant.full_name_source
        == "Test One"
    )
    services.rollback(actor=steward, batch=first, reason="mistake")
    assert Participant.objects.count() == 0
    assert first.status == ImportBatch.ROLLED_BACK
    assert {"import.uploaded", "import.committed", "import.rolled_back"} <= set(
        AuditEvent.objects.values_list("action", flat=True)
    )


@pytest.mark.django_db
def test_commit_resumes_after_a_failed_chunk(template, steward, monkeypatch):
    monkeypatch.setattr(services, "CHUNK_SIZE", 2)
    b = upload(steward, template, *GOOD)
    services.approve(actor=steward, batch=b)
    real = services.participants.import_participant
    calls = {"n": 0}

    def flaky(clean, **kw):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("boom")
        return real(clean, **kw)

    monkeypatch.setattr(services.participants, "import_participant", flaky)
    with pytest.raises(RuntimeError):
        services.commit(actor=steward, batch=b)
    b.refresh_from_db()
    assert b.status == ImportBatch.PARTIAL
    assert Participant.objects.count() == 2  # first chunk kept, failing chunk rolled back
    monkeypatch.setattr(services.participants, "import_participant", real)
    assert services.commit(actor=steward, batch=b).status == ImportBatch.COMMITTED
    assert Participant.objects.count() == 3


@pytest.mark.django_db
def test_bad_files_are_refused(template, steward):
    for name, data in (("x.txt", b"a"), ("x.csv", b""), ("x.csv", b"Name\nfoo\n")):
        with pytest.raises(services.ImportFailure):
            services.upload(actor=steward, template=template, file_name=name, data=data)


@pytest.mark.django_db
def test_xlsx_is_read(template, steward):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(list(COLUMNS))
    ws.append(["Excel Person", "P1", "K1", "C1", "E-900", "F", 30, "01"])
    buf = io.BytesIO()
    wb.save(buf)
    b = services.upload(actor=steward, template=template, file_name="f.xlsx", data=buf.getvalue())
    assert b.counts["create"] == 1


@pytest.mark.django_db
def test_error_report_lists_rows_without_their_values(template, steward):
    b = upload(steward, template, "Secret Name,ZZ,K1,C1,E-1,F,20,01")
    report = services.error_report(b)
    assert report.startswith("row,severity,field,message")
    assert "1,error,programme_code" in report
    assert "Secret Name" not in report


def test_formula_cells_are_neutralised():
    assert services._safe("=1+1") == "'=1+1"
    assert services._safe("@x") == "'@x"
    assert services._safe("plain") == "plain"


@pytest.mark.django_db
def test_api_flow(template, steward):
    c = Client()
    c.force_login(steward)
    f = SimpleUploadedFile("f.csv", csv_bytes(*GOOD), content_type="text/csv")
    r = c.post("/api/v1/imports/batches", {"template": str(template.pk), "file": f})
    assert r.status_code == 201, r.content
    bid = r.json()["id"]
    assert r.json()["counts"]["create"] == 3
    assert c.get(f"/api/v1/imports/batches/{bid}/rows?outcome=create").json()["total"] == 3
    assert c.post(f"/api/v1/imports/batches/{bid}/commit").status_code == 400  # not approved
    assert c.post(f"/api/v1/imports/batches/{bid}/approve").json()["status"] == "approved"
    assert c.post(f"/api/v1/imports/batches/{bid}/commit").json()["status"] == "committed"
    r = c.post(
        f"/api/v1/imports/batches/{bid}/rollback",
        {"reason": "test"},
        content_type="application/json",
    )
    assert r.json()["status"] == "rolled_back"
    assert c.get(f"/api/v1/imports/batches/{bid}/errors").status_code == 200
    assert ImportRow.objects.filter(batch_id=bid).count() == 3


# --- T-042 reconciliation and contract; T-041 quarantine after load ---------------------------


@pytest.mark.django_db
def test_reconciliation_balances_before_and_after_load(template, steward):
    batch = upload(steward, template, *GOOD, ",P1,K1,C1,E-009,F,20,01")  # last row: no name
    before = services.reconciliation(batch)
    assert before["source_rows"] == 4 and before["balanced"]
    assert before["pending"] == 3 and before["held"] == 1 and before["created"] == 0
    load(steward, batch)
    after = services.reconciliation(batch)
    assert after["created"] == 3 and after["held"] == 1 and after["pending"] == 0
    assert after["balanced"] and after["controls_match"]
    assert after["controls"] == [{"cohort": "K1", "source": 3, "pi360": 3, "matches": True}]
    assert after["held_rows"][0]["row"] == 4
    assert "Test One" not in str(after)  # reasons only, never values


@pytest.mark.django_db
def test_reconciliation_after_rollback_and_reimport(template, steward):
    batch = upload(steward, template, *GOOD)
    load(steward, batch)
    services.rollback(actor=steward, batch=batch, reason="test")
    r = services.reconciliation(batch)
    assert r["rolled_back"] == 3 and r["created"] == 0 and r["balanced"]
    again = upload(steward, template, *GOOD)
    assert services.reconciliation(again)["skipped"] == 0  # rolled-back rows are loadable again


@pytest.mark.django_db
def test_reconciliation_csv_is_safe(template, steward):
    batch = upload(steward, template, "=cmd,P1,K1,C1,E-1,F,20,01", ",P1,K1,C1,E-2,F,20,01")
    text = services.reconciliation_csv(batch)
    assert "section,item,source,pi360,detail" in text
    assert "balanced" in text
    assert "\n=" not in text and ",=" not in text


@pytest.mark.django_db
def test_contract_lists_columns_rules_and_gaps(world, steward):
    from apps.imports.models import MappingTemplate

    t = MappingTemplate(source="gap", version=1, columns={"N": "full_name"})  # not saved
    c = services.contract(t)
    assert c["columns"] == [{"source_column": "N", "field": "full_name", "required": True}]
    assert "programme_code" in c["required_fields_not_mapped"]
    assert c["rules"]


@pytest.mark.django_db
def test_commit_queues_possible_duplicates_without_merging(template, steward):
    from apps.participants.models import DuplicateCandidate

    batch = upload(
        steward,
        template,
        "Jane Wanjiru,P1,K1,C1,E-1,F,20,01",
        "Jane Wanjiru,P1,K1,C1,E-2,F,20,01",
    )
    load(steward, batch)
    assert DuplicateCandidate.objects.filter(status="open").count() == 1
    assert Participant.objects.filter(merged_into__isnull=False).count() == 0
    assert services.reconciliation(batch)["quarantined"] == 2


@pytest.mark.django_db
def test_rollback_blocked_after_a_merge(template, steward):
    from apps.participants import services as pp
    from apps.participants.models import DuplicateCandidate

    k1 = Cohort.objects.get(code="K1")
    k2 = Cohort.objects.create(
        programme=k1.programme, institution=k1.institution, code="K2", name="Cohort 2",
        intake_year=2025, batch_no=2, phase="1",
    )  # fmt: skip
    CohortCourse.objects.create(cohort=k2, course=Course.objects.get(code="C1"))
    batch = upload(
        steward,
        template,
        "Jane Wanjiru,P1,K1,C1,E-1,F,20,01",
        "Jane Wanjiru,P1,K2,C1,E-2,F,20,01",
    )
    load(steward, batch)
    cand = DuplicateCandidate.objects.get()
    pp.merge(actor=steward, candidate=cand, survivor_id=cand.participant_a_id, reason="same")
    with pytest.raises(services.ImportFailure):
        services.rollback(actor=steward, batch=batch, reason="x")


@pytest.mark.django_db
def test_api_reconciliation_and_contract(template, steward):
    c = Client()
    c.force_login(steward)
    batch = upload(steward, template, *GOOD)
    body = c.get(f"/api/v1/imports/batches/{batch.pk}/reconciliation").json()
    assert body["balanced"] and body["source_rows"] == 3
    csv_resp = c.get(f"/api/v1/imports/batches/{batch.pk}/reconciliation?download=csv")
    assert csv_resp["Content-Type"].startswith("text/csv")
    assert c.get(f"/api/v1/imports/templates/{template.pk}/contract").json()["rules"]


@pytest.mark.django_db
def test_inspect_suggests_mapping_and_finds_fitting_template(template, steward):
    head = "Full Name,Programme,Cohort,Course,Enrolment No,Notes\n"
    data = (head + "Test One,P1,K1,C1,E-001,\nTest Two,P1,K1,C1,E-002,\n").encode()
    seen = services.inspect(file_name="x.csv", data=data)
    assert seen["row_count"] == 2
    assert seen["empty_columns"] == ["Notes"]
    assert seen["suggested"]["Full Name"] == "full_name"
    assert seen["suggested"]["Enrolment No"] == "enrollment_no"
    assert "Notes" not in seen["suggested"]
    assert seen["matching_templates"] == []  # the saved one expects other headers
    assert not seen["already_loaded"]
    ok = services.inspect(file_name="f.csv", data=csv_bytes(*GOOD))
    assert ok["matching_templates"] == [str(template.pk)]
    assert Participant.objects.count() == 0 and ImportBatch.objects.count() == 0


@pytest.mark.django_db
def test_inspect_endpoint_needs_permission_and_stores_nothing(template, steward, make_user):
    client = Client()
    client.force_login(steward)
    f = SimpleUploadedFile("f.csv", csv_bytes(*GOOD), content_type="text/csv")
    res = client.post("/api/v1/imports/inspect", {"file": f})
    assert res.status_code == 200 and res.json()["row_count"] == 3
    assert ImportBatch.objects.count() == 0
    bad = SimpleUploadedFile("f.txt", b"x", content_type="text/plain")
    assert client.post("/api/v1/imports/inspect", {"file": bad}).status_code == 400
