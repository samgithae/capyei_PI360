import datetime

import pytest
from django.db import IntegrityError, transaction

from apps.configuration.models import (
    Cohort,
    CohortCourse,
    County,
    Course,
    Programme,
    TrainingInstitution,
)
from apps.identity.models import ScopeAssignment
from apps.participants.models import (
    Participant,
    ParticipantContact,
    ParticipantEnrollment,
    ParticipantResidence,
    SourceIdentifier,
)


@pytest.fixture
def world(db):
    prog = Programme.objects.create(code="P1", name="Programme One")
    prog2 = Programme.objects.create(code="P2", name="Programme Two")
    county = County.objects.get(code="01")
    inst = TrainingInstitution.objects.create(code="I1", name="College", county=county)
    course = Course.objects.create(programme=prog, code="C1", name="Course")
    cohorts = []
    for i, p in enumerate((prog, prog2), start=1):
        co = Cohort.objects.create(
            programme=p,
            institution=inst,
            code=f"K{i}",
            name=f"Cohort {i}",
            intake_year=2025,
            batch_no=i,
            phase="1",
            year_of_study=1,
        )
        cohorts.append(
            CohortCourse.objects.create(
                cohort=co,
                course=Course.objects.get_or_create(
                    programme=p, code="C1", defaults={"name": "Course"}
                )[0],
            )
        )
    return {"progs": (prog, prog2), "inst": inst, "ccs": cohorts, "course": course}


def enrol(w, person, idx=0, no=""):
    cc = w["ccs"][idx]
    return ParticipantEnrollment.objects.create(
        participant=person,
        cohort_course=cc,
        programme=w["progs"][idx],
        institution=w["inst"],
        source_enrollment_no=no,
    )


def scope(user, kind, value):
    ScopeAssignment.objects.create(user=user, kind=kind, value=str(value))


def test_status_and_gender_have_unknown_states(db):
    p = Participant.objects.create(full_name_source="Test Person")
    assert p.status == "unknown" and p.gender == "unknown"


def test_enrollment_no_unique_per_programme_only(world):
    a, b = (Participant.objects.create(full_name_source=n) for n in "AB")
    enrol(world, a, 0, "E1")
    with pytest.raises(IntegrityError), transaction.atomic():
        enrol(world, b, 0, "E1")
    enrol(world, b, 1, "E1")  # same number in another programme is fine
    c = Participant.objects.create(full_name_source="C")
    enrol(world, c, 0, "")
    d = Participant.objects.create(full_name_source="D")
    enrol(world, d, 0, "")  # blank numbers do not collide


def test_one_open_residence_and_one_primary_contact_per_kind(db):
    p = Participant.objects.create(full_name_source="P")
    ParticipantResidence.objects.create(
        participant=p, valid_from=datetime.date(2024, 1, 1), valid_to=datetime.date(2024, 6, 1)
    )
    ParticipantResidence.objects.create(participant=p)
    with pytest.raises(IntegrityError), transaction.atomic():
        ParticipantResidence.objects.create(participant=p)
    ParticipantContact.objects.create(participant=p, kind="phone", value="1", is_primary=True)
    ParticipantContact.objects.create(participant=p, kind="email", value="a@x", is_primary=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        ParticipantContact.objects.create(participant=p, kind="phone", value="2", is_primary=True)


def test_source_identifier_unique(db):
    p = Participant.objects.create(full_name_source="P")
    SourceIdentifier.objects.create(participant=p, source="sheet", identifier="9")
    with pytest.raises(IntegrityError), transaction.atomic():
        SourceIdentifier.objects.create(participant=p, source="sheet", identifier="9")


def test_scope_denies_without_assignment_and_allows_all_scope(world, make_user):
    p = Participant.objects.create(full_name_source="P")
    enrol(world, p)
    assert not Participant.objects.visible_to(make_user("none", "Placement officer")).exists()
    assert Participant.objects.visible_to(make_user("adm", "Administrator")).count() == 1


def test_scope_by_programme_cohort_region_officer_and_no_duplicates(world, make_user):
    u = make_user("o", "Placement officer")
    a = Participant.objects.create(full_name_source="A")
    b = Participant.objects.create(
        full_name_source="B", origin_county=County.objects.get(code="02")
    )
    enrol(world, a, 0)
    enrol(world, a, 1)  # two enrollments must not return A twice
    enrol(world, b, 1)
    scope(u, "programme", world["progs"][0].pk)
    scope(u, "programme", world["progs"][1].pk)
    assert sorted(Participant.objects.visible_to(u).values_list("full_name_source", flat=True)) == [
        "A",
        "B",
    ]
    scope(u, "region", County.objects.get(code="02").pk)  # AND across kinds
    assert list(Participant.objects.visible_to(u).values_list("full_name_source", flat=True)) == [
        "B"
    ]


def test_scope_by_officer_self_and_cohort(world, make_user):
    u = make_user("o2", "Placement officer")
    a = Participant.objects.create(full_name_source="Mine", assigned_officer=u)
    Participant.objects.create(full_name_source="Other")
    scope(u, "officer", "self")
    assert list(Participant.objects.visible_to(u)) == [a]
    u2 = make_user("o3", "Placement officer")
    enrol(world, a, 0)
    scope(u2, "cohort", world["ccs"][0].cohort_id)
    assert list(Participant.objects.visible_to(u2)) == [a]
