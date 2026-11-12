"""Bulk import of youth capability facts: matching, add-only, source, scope, preview. Synthetic."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.configuration.models import (
    Cohort,
    CohortCourse,
    County,
    Course,
    Programme,
    TrainingInstitution,
)
from apps.participants.models import (
    Participant,
    ParticipantEnrollment,
    ParticipantQualification,
    ParticipantReadiness,
    ParticipantSkill,
)

URL = "/api/v1/participants/profile-import"
HEAD = "enrollment_no,programme,type,value,detail,months,year\n"


def api(user):
    c = Client()
    c.force_login(user)
    return c


def youth(db, no="E-1"):
    prog = Programme.objects.create(code="P1", name="Programme One")
    inst = TrainingInstitution.objects.create(
        code="I1", name="College", county=County.objects.get(code="01")
    )
    course = Course.objects.create(programme=prog, code="C1", name="Course")
    co = Cohort.objects.create(
        programme=prog, institution=inst, code="K1", name="K", intake_year=2025,
        batch_no=1, phase="1", year_of_study=1,
    )  # fmt: skip
    cc = CohortCourse.objects.create(cohort=co, course=course)
    p = Participant.objects.create(full_name_source="Test Youth")
    ParticipantEnrollment.objects.create(
        participant=p, cohort_course=cc, programme=prog, institution=inst, source_enrollment_no=no
    )
    return p


def upload(user, text, dry=False):
    f = SimpleUploadedFile("facts.csv", text.encode(), content_type="text/csv")
    return api(user).post(URL, {"file": f, "dry_run": "1" if dry else ""})


def test_import_adds_unverified_import_facts_and_is_rerunnable(db, make_user):
    p = youth(db)
    admin = make_user("admin", "Administrator")
    rows = (
        HEAD
        + "E-1,P1,qualification,QL05,Diploma in Food,,2023\n"
        + "E-1,,skill,Welding,advanced,,\n"
        + "E-1,,availability,2026-12-01,full time,,\n"
        + "E-1,,experience,Cook,Acme,18,\n"
    )
    body = upload(admin, rows).json()
    assert body["failed"] == 0, body
    assert body["added_total"] == 4 and body["youth"] == 1
    q = ParticipantQualification.objects.get(participant=p)
    assert (q.source, q.verified, q.year_awarded) == ("import", False, 2023)
    assert ParticipantSkill.objects.get(participant=p).proficiency == 3
    assert ParticipantReadiness.objects.get(participant=p).work_patterns == ["full_time"]
    again = upload(admin, rows).json()
    assert again["added_total"] == 0 and again["skipped"] == 4
    assert ParticipantQualification.objects.filter(participant=p).count() == 1


def test_dry_run_saves_nothing_and_bad_rows_are_reported(db, make_user):
    p = youth(db)
    admin = make_user("admin", "Administrator")
    rows = HEAD + "E-1,,skill,Welding,,,\nE-9,,skill,Welding,,,\nE-1,,skill,Nope,,,\n"
    body = upload(admin, rows, dry=True).json()
    assert body["added_total"] == 1 and body["failed"] == 2
    assert {e["row"] for e in body["errors"]} == {3, 4}
    assert not ParticipantSkill.objects.filter(participant=p).exists()


def test_scope_and_permission(db, make_user):
    youth(db)
    steward = make_user("steward", "Data steward")
    assert upload(steward, HEAD + "E-1,,skill,Welding,,,\n").status_code == 200
    viewer = make_user("viewer", "M&E analyst")
    assert upload(viewer, HEAD + "E-1,,skill,Welding,,,\n").status_code == 403
    assert api(steward).get(URL + "-template").status_code == 200
    assert upload(steward, "a,b\n1,2\n").status_code == 400
