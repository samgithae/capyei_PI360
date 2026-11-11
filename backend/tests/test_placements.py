"""T-087 stage A: placement history is append-only, reviewed by a steward, and audited."""

import pytest

from apps.audit.models import AuditEvent
from apps.employers.models import Employer
from apps.participants.models import Participant, ParticipantEnrollment
from apps.placements import services as placements
from apps.placements.models import Placement

from .test_participants import enrol, world  # noqa: F401


@pytest.fixture
def enrollment(world):  # noqa: F811
    person = Participant.objects.create(full_name_source="Test Person")
    return enrol(world, person)


def test_record_keeps_source_text_and_leaves_status_unmapped(enrollment):
    p = placements.record(
        actor=None,
        enrollment_id=enrollment.pk,
        source_status="Employment",
        employer_name_source="  Acme Ltd ",
        designation="Welder",
    )
    assert p.employer_id is None and p.employer_name_source == "Acme Ltd"
    assert p.pathway == "" and p.status == ""
    assert AuditEvent.objects.filter(action="placement.recorded", object_id=str(p.pk)).exists()


def test_a_second_placement_is_a_new_row(enrollment):
    for s in ("Employment", "Further Studies"):
        placements.record(actor=None, enrollment_id=enrollment.pk, source_status=s)
    assert len(placements.for_enrollment(enrollment.pk)) == 2


def test_requires_source_status_known_pathway_and_enrollment(enrollment):
    with pytest.raises(placements.PlacementError):
        placements.record(actor=None, enrollment_id=enrollment.pk, source_status=" ")
    with pytest.raises(placements.PlacementError):
        placements.record(
            actor=None, enrollment_id=enrollment.pk, source_status="x", pathway="nonsense"
        )
    with pytest.raises(placements.PlacementError):
        placements.record(
            actor=None, enrollment_id=ParticipantEnrollment.objects.count() + 999, source_status="x"
        )


def test_review_links_employer_and_verifies(enrollment, make_user):
    steward = make_user("stew", "Data steward")
    emp = Employer.objects.create(name="Acme Ltd")
    p = placements.record(actor=steward, enrollment_id=enrollment.pk, source_status="Employment")
    p = placements.review(
        actor=steward, placement_id=p.pk, employer_id=emp.pk, pathway="wage", verified=True
    )
    assert p.employer_id == emp.pk and p.pathway == "wage"
    assert p.verified_by_id == steward.pk and p.verified_on is not None
    assert AuditEvent.objects.filter(action="placement.reviewed", object_id=str(p.pk)).exists()


def test_reported_facts_cannot_be_changed_or_deleted(enrollment):
    p = placements.record(actor=None, enrollment_id=enrollment.pk, source_status="Employment")
    p.source_status = "Entrepreneur"
    with pytest.raises(ValueError):
        p.save()
    with pytest.raises(ValueError):
        p.delete()
    assert Placement.objects.get(pk=p.pk).source_status == "Employment"
