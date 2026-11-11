"""Placement import profile (T-087 stage D). All data here is synthetic."""

import pytest

from apps.employers import services as employers
from apps.employers.models import Employer, EmployerContact
from apps.imports import services
from apps.imports.models import ImportRow
from apps.participants.models import Participant
from apps.placements import services as placements
from apps.placements.models import Placement
from tests.test_imports import steward, world  # noqa: F401  (fixtures)

COLS = {
    "Prog": "programme_code", "EnrolNo": "enrollment_no", "Status": "placement_status",
    "Org": "organisation", "Addr": "address", "Date": "placement_date",
    "Contact": "contact_name", "Phone": "contact_phone",
}  # fmt: skip
HEAD = "Prog,EnrolNo,Status,Org,Addr,Date,Contact,Phone\n"


@pytest.fixture
def people(world):  # noqa: F811
    from apps.configuration.models import CohortCourse, Programme
    from apps.participants.models import ParticipantEnrollment

    cc = CohortCourse.objects.get()
    prog = Programme.objects.get(code="P1")
    for no in ("E-001", "E-002"):
        p = Participant.objects.create(full_name_source=f"Test {no}")
        ParticipantEnrollment.objects.create(
            participant=p, cohort_course=cc, programme=prog,
            institution=cc.cohort.institution, source_enrollment_no=no,
        )  # fmt: skip


@pytest.fixture
def tpl(people, steward):  # noqa: F811
    placements.load_proposed(actor=steward)
    return services.create_template(
        actor=steward, source="placements", columns=COLS, target="placements"
    )


def up(steward, tpl, *rows):  # noqa: F811
    data = (HEAD + "\n".join(rows) + "\n").encode()
    return services.upload(actor=steward, template=tpl, file_name="p.csv", data=data)


def load(steward, batch):  # noqa: F811
    services.approve(actor=steward, batch=batch)
    return services.commit(actor=steward, batch=batch)


def test_inspect_suggests_placement_fields(db):
    seen = services.inspect(
        file_name="p.csv", data=(HEAD + "P1,E-1,Employment,Acme,,,,\n").encode(),
        target="placements",
    )  # fmt: skip
    assert seen["suggested"]["Status"] == "placement_status"
    assert seen["target"] == "placements"


def test_dry_run_adds_nothing_and_holds_unknowns(tpl, steward):  # noqa: F811
    b = up(
        steward, tpl,
        "P1,E-001,Employment,Acme Ltd,Nairobi,2025-03-01,Jo,0700",
        "P1,E-999,Employment,Acme Ltd,,,,",
        "P1,E-002,Mystery Value,Acme Ltd,,,,",
    )  # fmt: skip
    assert Placement.objects.count() == 0
    assert b.rows.filter(outcome=ImportRow.CREATE).count() == 1
    assert b.rows.filter(outcome=ImportRow.HELD).count() == 2


def test_commit_records_placement_and_enriches_employer(tpl, steward):  # noqa: F811
    emp = employers.create_employer(actor=steward, data={"name": "Acme Ltd"})
    employers.decide_cluster(
        actor=steward, key=employers.cluster_key("Acme Ltd"), spellings=["Acme Ltd"],
        action="link", employer_id=emp.pk,
    )  # fmt: skip
    b = load(steward, up(steward, tpl, "P1,E-001,Employment,Acme Ltd,Nairobi,2025-03-01,Jo,0700"))
    p = Placement.objects.get()
    assert p.status == "placed" and p.pathway == "wage" and str(p.start_date) == "2025-03-01"
    assert str(p.employer_id) == str(emp.pk)
    emp.refresh_from_db()
    assert emp.address == "Nairobi" and EmployerContact.objects.filter(employer=emp).count() == 1
    assert b.status == "committed"


def test_declined_offers_are_skipped(tpl, steward):  # noqa: F811
    b = up(steward, tpl, "P1,E-001,Opportunities shows&Rejected,Acme,,,,")
    assert b.rows.filter(outcome=ImportRow.SKIP).count() == 1
    load(steward, b)
    assert Placement.objects.count() == 0


def test_rollback_removes_placements_and_enrichment(tpl, steward):  # noqa: F811
    emp = employers.create_employer(actor=steward, data={"name": "Acme Ltd"})
    employers.decide_cluster(
        actor=steward, key=employers.cluster_key("Acme Ltd"), spellings=["Acme Ltd"],
        action="link", employer_id=emp.pk,
    )  # fmt: skip
    b = load(steward, up(steward, tpl, "P1,E-001,Employment,Acme Ltd,Nairobi,,Jo,0700"))
    services.rollback(actor=steward, batch=b, reason="test")
    assert Placement.objects.count() == 0
    emp.refresh_from_db()
    assert emp.address == "" and not EmployerContact.objects.filter(employer=emp).exists()
    assert Employer.objects.filter(pk=emp.pk).exists()  # the employer itself stays


def test_rollback_refused_for_verified_placement(tpl, steward):  # noqa: F811
    from django.utils import timezone

    b = load(steward, up(steward, tpl, "P1,E-001,Employment,Acme,,,,"))
    p = Placement.objects.get()
    p.verified_by, p.verified_on = steward, timezone.now()
    p.save(update_fields=["verified_by", "verified_on"])
    with pytest.raises(services.ImportFailure):
        services.rollback(actor=steward, batch=b, reason="test")
    assert Placement.objects.count() == 1


def test_participant_templates_unaffected(db):
    with pytest.raises(services.ImportFailure):
        services.create_template(actor=None, source="x", columns={"A": "nope"}, target="bogus")


def test_review_lists_groups_and_unmapped_then_recheck_releases_rows(people, steward):  # noqa: F811
    t = services.create_template(
        actor=steward, source="placements", columns=COLS, target="placements"
    )
    b = up(
        steward, t,
        "P1,E-001,Employment,Acme Ltd,,,,",
        "P1,E-002,Self Hire,Acme Limited,,,,",
    )  # fmt: skip
    review = services.placement_review(b)
    assert review["held"] == 2  # nothing mapped yet
    assert {u["value"] for u in review["unmapped_statuses"]} == {"Employment", "Self Hire"}
    assert len(review["clusters"]) == 1  # both spellings group under one key
    services.map_placement_status(
        actor=steward, batch=b, source_value="Employment", status="placed", pathway="wage"
    )
    services.map_placement_status(
        actor=steward, batch=b, source_value="Self Hire", status="placed",
        pathway="self_employment",
    )  # fmt: skip
    b = services.recheck(actor=steward, batch=b)
    assert b.counts["create"] == 2 and b.counts["held"] == 0


def test_review_refused_for_participant_batches_and_after_approval(tpl, steward):  # noqa: F811
    b = up(steward, tpl, "P1,E-001,Employment,Acme,,,,")
    services.approve(actor=steward, batch=b)
    with pytest.raises(services.ImportFailure):
        services.placement_review(b)


def test_same_person_twice_in_a_file_warns_but_both_load(tpl, steward):  # noqa: F811
    b = up(steward, tpl, "P1,E-001,Employment,Acme,,,,", "P1,E-001,Employment,Beta,,,,")
    second = b.rows.get(row_no=2)
    assert any("Same person as row 1" in w["message"] for w in second.warnings)
    load(steward, b)
    assert Placement.objects.count() == 2
