"""Data quality and MIS corrections (T-074, D-025 option a).

An officer's fix to a value the MIS owns is kept with who made it, listed for the MIS update, and
protected from the next import until the MIS agrees or a reviewer decides."""

import csv
import io
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.configuration.models import County
from apps.identity import services as identity
from apps.participants import services as participants
from apps.participants.models import (
    Participant,
    ParticipantContact,
    ParticipantCorrection,
    ParticipantEnrollment,
)
from apps.reporting.models import ExportLog

from .test_participants import enrol, world  # noqa: F401

JSON = "application/json"


def client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def admin(make_user):
    user = make_user("adm", "Administrator")
    identity.grant_permission(
        actor=user,
        user=user,
        permission="exports.identifiable",
        purpose="MIS update",
        expires_at=timezone.now() + timedelta(days=3),
    )
    return user


@pytest.fixture
def ann(world):  # noqa: F811
    """A youth that came from the MIS: Project One, number E1."""
    p = Participant.objects.create(
        full_name_source="Ann Wanjiru",
        gender="female",
        age_at_source=20,
        origin_county=County.objects.get(code="01"),
    )
    e = enrol(world, p, 0, "E1")
    e.status = "enrolled"
    e.save()
    return p


def patch(user, path, body):
    return client(user).patch(f"/api/v1/participants/{path}", body, content_type=JSON)


def clean_row(**kw):
    """What the importer hands over for the row of project P1 number E1."""
    c = County.objects.get(code="01")
    row = {
        "full_name": "Ann Wanjiru", "gender": "female", "age": 20, "status": "enrolled",
        "county_code": "01", "phone": "", "email": "", "source_id": "", "enrollment_no": "E1",
        "project_code": "P1", "cohort_code": "K1", "course_code": "C1", "extra": {},
        "_refs": {"offering": None, "project": None, "county": str(c.pk)},
    }  # fmt: skip
    row.update(kw)
    return row


def run_import(world, **kw):  # noqa: F811
    row = clean_row(**kw)
    row["_refs"]["project"] = world["progs"][0].pk
    if "county" in kw:
        row["_refs"]["county"] = kw["county"]
    return participants.import_participant(row, batch_ref="batch-0001")


# --- recording the officer's fix ---------------------------------------------------------------


@pytest.mark.django_db
def test_editing_an_mis_value_records_a_correction(admin, ann):
    other = County.objects.get(code="02")
    r = patch(admin, ann.pk, {"gender": "male", "origin_county_id": str(other.pk)})
    assert r.status_code == 200
    rows = {c.field: c for c in ParticipantCorrection.objects.filter(participant=ann)}
    assert set(rows) == {"gender", "county"}
    assert rows["gender"].before_label == "Female" and rows["gender"].after_label == "Male"
    assert rows["county"].after_label == other.name
    assert rows["county"].created_by == admin and rows["county"].state == "open"


@pytest.mark.django_db
def test_values_the_mis_does_not_own_are_not_tracked(admin, ann):
    patch(admin, ann.pk, {"given_name": "Ann", "date_of_birth": "2005-01-02"})
    assert not ParticipantCorrection.objects.exists()


@pytest.mark.django_db
def test_a_youth_not_from_the_mis_has_nothing_to_correct(admin, world):  # noqa: F811
    p = Participant.objects.create(full_name_source="Walk In", gender="male")
    enrol(world, p, 0, "")  # no MIS number
    patch(admin, p.pk, {"gender": "female"})
    assert not ParticipantCorrection.objects.exists()


@pytest.mark.django_db
def test_a_second_edit_updates_the_open_correction_and_keeps_the_mis_value(admin, ann):
    patch(admin, ann.pk, {"age_at_source": 21})
    patch(admin, ann.pk, {"age_at_source": 22})
    (c,) = ParticipantCorrection.objects.all()
    assert (c.before_label, c.after_label) == ("20", "22")


@pytest.mark.django_db
def test_putting_the_value_back_withdraws_the_correction(admin, ann):
    patch(admin, ann.pk, {"age_at_source": 21})
    patch(admin, ann.pk, {"age_at_source": 20})
    assert not ParticipantCorrection.objects.exists()


@pytest.mark.django_db
def test_enrolment_status_is_tracked_per_enrolment(admin, ann):
    e = ann.enrollments.get()
    r = client(admin).patch(
        f"/api/v1/participants/{ann.pk}/enrollments/{e.pk}",
        {"status": "completed"},
        content_type=JSON,
    )
    assert r.status_code == 200
    (c,) = ParticipantCorrection.objects.all()
    assert (c.field, c.enrollment_id, c.after_label) == ("status", e.pk, "Completed")


# --- the import may not overwrite a fix --------------------------------------------------------


@pytest.mark.django_db
def test_import_holds_back_a_corrected_field_and_notes_the_conflict(admin, ann, world):  # noqa: F811
    patch(admin, ann.pk, {"gender": "male"})
    action, _pid, _before, after = run_import(world, gender="female", age=25)
    assert action == "update"
    ann.refresh_from_db()
    assert ann.gender == "male"  # the fix stands
    assert ann.age_at_source == 25  # an uncorrected field still follows the file
    assert after["age"] == 25
    c = ParticipantCorrection.objects.get()
    assert c.state == "open"
    assert (c.conflict_label, c.conflict_batch) == ("Female", "batch-0001")
    assert c.conflict_at is not None


@pytest.mark.django_db
def test_import_that_matches_the_fix_closes_it(admin, ann, world):  # noqa: F811
    patch(admin, ann.pk, {"gender": "male"})
    run_import(world, gender="male")
    c = ParticipantCorrection.objects.get()
    assert (c.state, c.closed_how) == ("confirmed", "mis_matched")
    ann.refresh_from_db()
    assert ann.gender == "male"
    # With the fix closed, the next import is free to change it again.
    run_import(world, gender="other")
    ann.refresh_from_db()
    assert ann.gender == "other"


@pytest.mark.django_db
def test_an_unknown_value_in_the_file_never_counts_as_a_conflict(admin, ann, world):  # noqa: F811
    patch(admin, ann.pk, {"gender": "male"})
    run_import(world, gender="unknown")
    assert ParticipantCorrection.objects.get().conflict_at is None


@pytest.mark.django_db
def test_import_cannot_overwrite_a_corrected_status(admin, ann, world):  # noqa: F811
    e = ann.enrollments.get()
    client(admin).patch(
        f"/api/v1/participants/{ann.pk}/enrollments/{e.pk}",
        {"status": "withdrawn"},
        content_type=JSON,
    )
    run_import(world, status="enrolled")
    e.refresh_from_db()
    assert e.status == "withdrawn"


# --- a reviewer's decision ---------------------------------------------------------------------


def resolve(user, c, action, note=""):
    return client(user).post(
        f"/api/v1/participants/corrections/{c.pk}/resolve",
        {"action": action, "note": note},
        content_type=JSON,
    )


@pytest.fixture
def disputed(admin, ann, world):  # noqa: F811
    patch(admin, ann.pk, {"gender": "male"})
    run_import(world, gender="female")
    return ParticipantCorrection.objects.get()


@pytest.mark.django_db
def test_confirm_releases_the_guard(admin, ann, disputed, world):  # noqa: F811
    r = resolve(admin, disputed, "confirm", "Updated in the MIS on 3 Nov")
    assert r.status_code == 200 and r.json()["state"] == "confirmed"
    disputed.refresh_from_db()
    assert disputed.closed_by == admin and disputed.closed_how == "confirm"
    run_import(world, gender="female")
    ann.refresh_from_db()
    assert ann.gender == "female"  # nothing protects it any more
    assert AuditEvent.objects.filter(action="correction.resolved").count() == 1


@pytest.mark.django_db
def test_accept_takes_the_mis_value_and_closes_the_fix(admin, ann, disputed):
    r = resolve(admin, disputed, "accept")
    assert r.status_code == 200 and r.json()["state"] == "closed"
    ann.refresh_from_db()
    assert ann.gender == "female"


@pytest.mark.django_db
def test_keep_clears_the_conflict_but_the_fix_stays_protected(admin, ann, disputed, world):  # noqa: F811
    r = resolve(admin, disputed, "keep")
    assert r.status_code == 200 and r.json()["conflict"] is None
    disputed.refresh_from_db()
    assert disputed.state == "open"
    run_import(world, gender="female")
    ann.refresh_from_db()
    assert ann.gender == "male"
    disputed.refresh_from_db()
    assert disputed.conflict_at is not None  # raised again by the new file


@pytest.mark.django_db
def test_keep_and_accept_need_a_conflict_and_a_closed_fix_cannot_be_reopened(admin, ann):
    patch(admin, ann.pk, {"gender": "male"})
    c = ParticipantCorrection.objects.get()
    assert resolve(admin, c, "keep").status_code == 409
    assert resolve(admin, c, "accept").status_code == 409
    assert resolve(admin, c, "confirm").status_code == 200
    again = resolve(admin, c, "confirm")
    assert again.status_code == 409 and again.json()["errors"][0]["code"] == "closed"


@pytest.mark.django_db
def test_only_people_with_the_permission_can_see_or_decide(make_user, ann, admin):
    patch(admin, ann.pk, {"gender": "male"})
    c = ParticipantCorrection.objects.get()
    officer = make_user("off", "Placement officer")
    assert client(officer).get("/api/v1/participants/corrections").status_code == 403
    assert client(officer).get("/api/v1/participants/data-quality").status_code == 403
    assert resolve(officer, c, "confirm").status_code == 403


# --- the list ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_filters_by_state_and_counts_the_waiting_ones(admin, ann, disputed):
    other = Participant.objects.create(full_name_source="Bea Otieno", age_at_source=19)
    ParticipantCorrection.objects.create(
        participant=other, field="age", before_label="19", after_raw="20", after_label="20",
        state="confirmed",
    )  # fmt: skip
    get = lambda q="": client(admin).get(f"/api/v1/participants/corrections{q}").json()  # noqa: E731
    body = get()
    assert [r["participant"]["name"] for r in body["results"]] == ["Ann Wanjiru"]
    assert body["counts"] == {"open": 1, "conflict": 1}
    row = body["results"][0]
    assert (row["field_label"], row["was"], row["now"]) == ("Gender", "Female", "Male")
    assert row["conflict"]["value"] == "Female" and row["enrollment_no"] == "E1"
    assert row["project"] == "Project One"
    assert get("?state=confirmed")["total"] == 1
    assert get("?state=all")["total"] == 2
    assert get("?q=bea&state=all")["total"] == 1
    assert client(admin).get("/api/v1/participants/corrections?state=nope").status_code == 400


# --- the data-quality rules --------------------------------------------------------------------


@pytest.mark.django_db
def test_summary_counts_each_rule(admin, world):  # noqa: F811
    good = Participant.objects.create(
        full_name_source="Good Person", gender="male", age_at_source=22,
        origin_county=County.objects.get(code="01"), status="active",
    )  # fmt: skip
    ParticipantContact.objects.create(participant=good, kind="phone", value="0700000001")
    ge = enrol(world, good, 0, "G1")
    ge.status = "enrolled"
    ge.save()
    bad = Participant.objects.create(full_name_source="Madonna", age_at_source=9)
    enrol(world, bad, 0, "")
    body = client(admin).get("/api/v1/participants/data-quality").json()
    counts = {r["code"]: r["count"] for r in body["rules"]}
    assert body["checked"] == 2 and body["failing"] == 1
    assert counts["no_county"] == 1 and counts["gender_unknown"] == 1
    assert counts["age_range"] == 1 and counts["age_missing"] == 0
    assert counts["no_contact"] == 1 and counts["no_mis_number"] == 1
    assert counts["single_name"] == 1 and counts["status_unknown"] == 1


@pytest.mark.django_db
def test_records_list_the_rules_each_youth_fails(admin, world):  # noqa: F811
    bad = Participant.objects.create(full_name_source="Madonna")
    enrol(world, bad, 0, "M1")
    ok = Participant.objects.create(
        full_name_source="Fully Complete", gender="female", age_at_source=22,
        origin_county=County.objects.get(code="01"),
    )  # fmt: skip
    ParticipantContact.objects.create(participant=ok, kind="email", value="a@example.org")
    e = enrol(world, ok, 0, "F1")
    e.status = "enrolled"
    e.save()
    get = lambda q="": client(admin).get(f"/api/v1/participants/data-quality/records{q}")  # noqa: E731
    body = get().json()
    assert body["total"] == 1
    row = body["results"][0]
    assert row["name"] == "Madonna" and row["enrollment_numbers"] == ["M1"]
    codes = {i["code"] for i in row["issues"]}
    assert {"no_county", "gender_unknown", "age_missing", "single_name"} <= codes
    assert all(i["fix"] for i in row["issues"])
    assert get("?rule=single_name").json()["total"] == 1
    assert get("?rule=no_county&q=nobody").json()["total"] == 0
    assert get("?rule=nope").status_code == 400


@pytest.mark.django_db
def test_reversed_dates_are_flagged(admin, world):  # noqa: F811
    p = Participant.objects.create(
        full_name_source="Dates Wrong", gender="male", age_at_source=20,
        origin_county=County.objects.get(code="01"),
    )  # fmt: skip
    e = enrol(world, p, 0, "D1")
    e.enrolled_on, e.completed_on = timezone.localdate(), timezone.localdate() - timedelta(days=5)
    e.save()
    body = client(admin).get("/api/v1/participants/data-quality/records?rule=dates_reversed")
    assert body.json()["total"] == 1


# --- the correction export ---------------------------------------------------------------------


def export(user, query="", **body):
    return client(user).post(
        "/api/v1/exports/table/corrections" + query,
        {"format": "csv", "purpose": "MIS update", **body},
        content_type=JSON,
    )


def parse(resp):
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


@pytest.mark.django_db
def test_export_lists_the_fixes_waiting_for_the_mis(admin, ann, disputed):
    r = export(admin)
    assert r.status_code == 200
    head, *rows = parse(r)
    cell = lambda row, h: row[head.index(h)]  # noqa: E731
    assert len(rows) == 1
    assert cell(rows[0], "Youth") == "Ann Wanjiru"
    assert cell(rows[0], "MIS enrolment number") == "E1"
    assert (cell(rows[0], "Field"), cell(rows[0], "MIS value")) == ("Gender", "Female")
    assert cell(rows[0], "Corrected value") == "Male"
    assert cell(rows[0], "Corrected by") == "adm"
    assert cell(rows[0], "Value the last import tried to bring in") == "Female"


@pytest.mark.django_db
def test_export_state_filter_and_field_choice(admin, ann, disputed):
    resolve(admin, disputed, "confirm")
    assert export(admin).status_code == 409  # nothing is waiting any more
    r = export(admin, "?state=confirmed", fields=["name", "now"])
    head, *rows = parse(r)
    assert head == ["Youth", "Corrected value"] and rows == [["Ann Wanjiru", "Male"]]


@pytest.mark.django_db
def test_export_log_holds_no_names_or_values(admin, ann, disputed):
    assert export(admin).status_code == 200
    log = ExportLog.objects.get(dataset="corrections")
    assert log.row_count == 1 and log.detail["filters"] == {}
    blob = str(log.detail) + str(AuditEvent.objects.filter(action="export.created").values())
    assert "Ann" not in blob and "Wanjiru" not in blob


@pytest.mark.django_db
def test_export_needs_the_restricted_permission(make_user, ann):
    steward = make_user("stw", "Data steward")
    assert export(steward).status_code == 403


@pytest.mark.django_db
def test_the_picker_lists_the_correction_fields(admin):
    r = client(admin).get("/api/v1/exports/fields/corrections")
    keys = [f["key"] for g in r.json()["groups"] for f in g["fields"]]
    assert keys[:3] == ["name", "enrollment_no", "project"] and "now" in keys


@pytest.mark.django_db
def test_enrollment_model_is_untouched_by_a_held_back_import(admin, ann, world):  # noqa: F811
    patch(admin, ann.pk, {"age_at_source": 30})
    run_import(world, age=21)
    assert ann.enrollments.get().status == ParticipantEnrollment.ENROLLED
    ann.refresh_from_db()
    assert ann.age_at_source == 30
