"""Placement import profile (T-087 stage D). All data here is synthetic."""

from datetime import date

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
    "Prog": "project_code", "EnrolNo": "enrollment_no", "Status": "placement_status",
    "Org": "organisation", "Addr": "address", "Date": "placement_date",
    "Contact": "contact_name", "Phone": "contact_phone",
}  # fmt: skip
HEAD = "Prog,EnrolNo,Status,Org,Addr,Date,Contact,Phone\n"


@pytest.fixture
def people(world):  # noqa: F811
    from apps.configuration.models import CohortCourse, Project
    from apps.participants.models import ParticipantEnrollment

    cc = CohortCourse.objects.get()
    prog = Project.objects.get(code="P1")
    for no in ("E-001", "E-002"):
        p = Participant.objects.create(full_name_source=f"Test {no}")
        ParticipantEnrollment.objects.create(
            participant=p, cohort_course=cc, project=prog,
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


def test_a_second_running_row_in_one_file_is_held(tpl, steward):  # noqa: F811
    """D-081 with the provisional C-3 rule: the first running row for a youth loads, the next
    is held for review, not created."""
    b = up(steward, tpl, "P1,E-001,Employment,Acme,,,,", "P1,E-001,Employment,Beta,,,,")
    second = b.rows.get(row_no=2)
    assert second.outcome == "held"
    assert second.errors[0]["code"] == "second_running"
    assert "earlier row in this file" in second.errors[0]["message"]
    load(steward, b)
    assert Placement.objects.count() == 1


def test_a_row_for_a_youth_already_placed_is_held_until_the_old_one_ends(tpl, steward):  # noqa: F811
    first = load(steward, up(steward, tpl, "P1,E-001,Employment,Acme,,2026-03-01,,"))
    assert Placement.objects.count() == 1
    b = up(steward, tpl, "P1,E-001,Employment,Beta,,,,")
    row = b.rows.get(row_no=1)
    assert row.outcome == "held" and "running placement with Acme" in row.errors[0]["message"]
    running = Placement.objects.get()
    placements.end_episode(actor=steward, placement_id=running.pk, end_date=date(2026, 6, 30))
    b = services.recheck(actor=steward, batch=b)
    assert b.counts["create"] == 1 and b.counts["held"] == 0
    load(steward, b)
    assert Placement.objects.count() == 2 and first.status == "committed"


def test_a_placement_recorded_after_the_check_holds_the_row_at_commit(tpl, steward):  # noqa: F811
    b = up(steward, tpl, "P1,E-001,Employment,Acme,,,,")
    services.approve(actor=steward, batch=b)
    enrollment_id = b.rows.get(row_no=1).clean["_refs"]["enrollment"]
    placements.record(actor=steward, enrollment_id=enrollment_id, source_status="Employment")
    b = services.commit(actor=steward, batch=b)
    assert b.status == "committed" and b.counts["held"] == 1 and b.counts["create"] == 0
    assert Placement.objects.count() == 1


def test_an_ended_or_non_running_row_is_never_held(tpl, steward):  # noqa: F811
    placements.map_status(
        actor=steward, source_value="Studying", status="in_training", pathway="further_training"
    )
    b = up(steward, tpl, "P1,E-001,Employment,Acme,,,,", "P1,E-001,Studying,College,,,,")
    assert b.rows.get(row_no=2).outcome == "create"


# --- stage E: promote extra data ------------------------------------------------------------


@pytest.fixture
def wide(people):
    """Enrollments carrying placement text as extra, as a wide sheet leaves them."""
    from apps.participants.models import ParticipantEnrollment

    rows = {
        "E-001": {"Organisation": "Acme Ltd", "Placement Status": "Employment", "Note": "x"},
        "E-002": {"Organisation": "", "Placement Status": "Employment"},
    }
    for no, extra in rows.items():
        ParticipantEnrollment.objects.filter(source_enrollment_no=no).update(extra=extra)


MAP = {"Organisation": "organisation", "Placement Status": "placement_status"}


def test_extra_summary_counts_labels(wide):
    s = services.extra_summary("P1")
    got = {x["label"]: x["filled"] for x in s["labels"]}
    assert got == {"Organisation": 1, "Placement Status": 2, "Note": 1}
    assert s["enrollments"] == 2 and s["without_number"] == 0


def test_promote_validates_then_loads(wide, steward):  # noqa: F811
    placements.load_proposed(actor=steward)
    batch = services.promote_extra(actor=steward, project_code="p1", columns=MAP)
    assert batch.status == "validated" and batch.counts["total"] == 2
    assert Placement.objects.count() == 0  # a dry run changes nothing
    batch = load(steward, batch)
    assert Placement.objects.count() == 2
    assert batch.template.target == "placements"
    assert services.reconciliation(batch)["balanced"]


def test_promote_twice_adds_nothing(wide, steward):  # noqa: F811
    placements.load_proposed(actor=steward)
    load(steward, services.promote_extra(actor=steward, project_code="P1", columns=MAP))
    again = services.promote_extra(actor=steward, project_code="P1", columns=MAP)
    assert again.counts["skip"] == 2 and again.counts["create"] == 0


def test_promote_holds_unmapped_status_and_rolls_back(wide, steward):  # noqa: F811
    batch = services.promote_extra(actor=steward, project_code="P1", columns=MAP)
    assert batch.counts["held"] == 2  # no status map loaded yet
    placements.load_proposed(actor=steward)
    batch = services.recheck(actor=steward, batch=batch)
    batch = load(steward, batch)
    services.rollback(actor=steward, batch=batch, reason="test")
    assert Placement.objects.count() == 0


@pytest.mark.parametrize(
    "cols",
    [
        {"Organisation": "organisation"},  # no status
        {"Placement Status": "placement_status", "Organisation": "nonsense"},
        {"Placement Status": "placement_status", "Note": "placement_status"},
        {"Placement Status": "enrollment_no"},
        {"Missing": "placement_status"},  # label nobody has
    ],
)
def test_promote_refuses_bad_mappings(wide, steward, cols):  # noqa: F811
    with pytest.raises(services.ImportFailure):
        services.promote_extra(actor=steward, project_code="P1", columns=cols)


def test_promote_needs_some_value(people, steward):  # noqa: F811
    with pytest.raises(services.ImportFailure):
        services.promote_extra(
            actor=steward, project_code="P1", columns={"Placement Status": "placement_status"}
        )
