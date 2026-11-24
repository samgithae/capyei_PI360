"""D-081 (PI360-NEW-070): a youth has at most one running placement (placed and not ended).

The service refuses a second one across all of the youth's enrollments; the database refuses a
second one on the same enrollment, whatever path wrote it. All data here is synthetic."""

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.participants.models import Participant
from apps.placements import services as placements
from apps.placements.models import Placement

from .test_participants import enrol, world  # noqa: F401


@pytest.fixture
def youth(world):  # noqa: F811
    return Participant.objects.create(full_name_source="Test Person")


@pytest.fixture
def enrollment(world, youth):  # noqa: F811
    return enrol(world, youth)


def running(enrollment_id, **kw):
    return placements.record(
        actor=None, enrollment_id=enrollment_id, source_status="Employment",
        pathway="wage", status="placed", **kw,
    )  # fmt: skip


def test_the_database_refuses_two_running_on_one_enrollment(enrollment):
    running(enrollment.pk)
    with pytest.raises(IntegrityError), transaction.atomic():
        Placement.objects.create(
            enrollment=enrollment, source_status="x", status="placed", pathway="wage"
        )


def test_the_database_allows_ended_and_unmapped_rows_beside_a_running_one(enrollment):
    running(enrollment.pk)
    Placement.objects.create(
        enrollment=enrollment, source_status="x", status="placed", pathway="wage",
        start_date=date(2024, 1, 1), end_date=date(2024, 6, 1),
    )  # fmt: skip
    Placement.objects.create(enrollment=enrollment, source_status="Unmapped value")
    assert Placement.objects.count() == 3


def test_record_refuses_a_second_running_one_and_names_the_first(enrollment):
    first = running(enrollment.pk, employer_name_source="Acme Traders")
    with pytest.raises(placements.ActivePlacementExists) as caught:
        running(enrollment.pk, employer_name_source="Beta Ltd")
    assert caught.value.running == first and "Acme Traders" in str(caught.value)


def test_record_refuses_across_the_youths_enrollments(world, youth, enrollment):  # noqa: F811
    running(enrollment.pk)
    other = enrol(world, youth, idx=1)
    with pytest.raises(placements.ActivePlacementExists):
        running(other.pk)


def test_review_cannot_make_a_second_running_one(enrollment, make_user):
    running(enrollment.pk)
    held = placements.record(actor=None, enrollment_id=enrollment.pk, source_status="Odd value")
    with pytest.raises(placements.ActivePlacementExists):
        placements.review(actor=make_user("s"), placement_id=held.pk, status="placed")
    held.refresh_from_db()
    assert held.status == ""


def test_apply_mappings_leaves_a_second_running_row_unmapped(enrollment, make_user):
    steward = make_user("s")
    running(enrollment.pk)
    held = placements.record(actor=None, enrollment_id=enrollment.pk, source_status="Hired")
    placements.map_status(actor=steward, source_value="Hired", status="placed", pathway="wage")
    assert placements.apply_mappings(actor=steward) == 0
    held.refresh_from_db()
    assert held.status == ""  # still waiting for a person to review it


def test_change_employer_needs_a_running_placement(enrollment, make_user):
    old = running(enrollment.pk, start_date=date(2026, 1, 1))
    placements.end_episode(actor=None, placement_id=old.pk, end_date=date(2026, 3, 1))
    with pytest.raises(placements.PlacementError):
        placements.change_employer(
            actor=make_user("s"), placement_id=old.pk, end_date=date(2026, 3, 1),
            start_date=date(2026, 3, 2), pathway="wage", employer_name_source="Beta",
        )  # fmt: skip
