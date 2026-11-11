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


# --- Stage C: status mapping (D-061) -----------------------------------------------------------


@pytest.fixture
def steward(make_user):
    return make_user("stew", "Data steward")


def test_map_is_empty_by_default_and_blank_never_maps(db):
    assert placements.resolve_status("Employment") is None
    assert placements.resolve_status("  ") is None


def test_unmapped_values_lists_distinct_with_counts(db, steward):
    vals = ["Employment", "employment ", "Entrepreneur", "", None, "Entrepreneur", "Entrepreneur"]
    assert placements.unmapped_values(vals) == [
        {"value": "Entrepreneur", "count": 3},
        {"value": "Employment", "count": 2},
    ]
    placements.map_status(actor=steward, source_value="Employment", status="placed", pathway="wage")
    assert [u["value"] for u in placements.unmapped_values(vals)] == ["Entrepreneur"]


def test_map_status_validates_and_versions_changes(db, steward):
    with pytest.raises(placements.PlacementError):
        placements.map_status(actor=steward, source_value="", status="placed", pathway="wage")
    with pytest.raises(placements.PlacementError):
        placements.map_status(actor=steward, source_value="X", status="placed")  # no pathway
    with pytest.raises(placements.PlacementError):
        placements.map_status(actor=steward, source_value="X", status="placed", pathway="bad")
    a = placements.map_status(
        actor=steward, source_value="Employment", status="placed", pathway="wage"
    )
    b = placements.map_status(
        actor=steward, source_value="EMPLOYMENT", status="placed", pathway="self_employment"
    )
    assert a.pk == b.pk and b.version == 2 and b.pathway == "self_employment"
    assert AuditEvent.objects.filter(action="placement.status_mapped").count() == 2


def test_both_spellings_of_the_html_escaped_value_meet(db, steward):
    placements.load_proposed(actor=steward)
    for v in ("Opportunities shows&Rejected", "Opportunities shows&amp;Rejected"):
        m = placements.resolve_status(v)
        assert m is not None and m.is_placement is False and m.pathway == ""


def test_load_proposed_never_overwrites_a_choice(db, steward):
    placements.map_status(actor=steward, source_value="Employment", status="mine", pathway="wage")
    assert placements.load_proposed(actor=steward) == 3
    assert placements.resolve_status("Employment").status == "mine"
    assert placements.load_proposed(actor=steward) == 0


def test_record_fills_from_mapping_and_unmapped_stays_blank(enrollment, steward):
    placements.load_proposed(actor=steward)
    a = placements.record(actor=steward, enrollment_id=enrollment.pk, source_status="Employment")
    b = placements.record(actor=steward, enrollment_id=enrollment.pk, source_status="Odd value")
    c = placements.record(
        actor=steward, enrollment_id=enrollment.pk, source_status="Opportunities shows&Rejected"
    )
    assert (a.pathway, a.status) == ("wage", "placed")
    assert (b.pathway, b.status) == ("", "")
    assert (c.pathway, c.status) == ("", "")  # a referral outcome is not turned into a placement


def test_apply_mappings_fills_only_blank_rows(enrollment, steward):
    early = placements.record(
        actor=steward, enrollment_id=enrollment.pk, source_status="Employment"
    )
    reviewed = placements.record(
        actor=steward, enrollment_id=enrollment.pk, source_status="Employment",
        pathway="self_employment", status="checked",
    )  # fmt: skip
    assert early.status == ""
    placements.map_status(actor=steward, source_value="Employment", status="placed", pathway="wage")
    assert placements.apply_mappings(actor=steward) == 1
    early.refresh_from_db(), reviewed.refresh_from_db()
    assert (early.pathway, early.status) == ("wage", "placed")
    assert (reviewed.pathway, reviewed.status) == ("self_employment", "checked")
    assert placements.apply_mappings(actor=steward) == 0
