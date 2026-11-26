"""Follow-up outcomes, employment type and salary (PI360-NEW-034/035/036, B25, A3). Synthetic
data only.

Acceptance: a check-in records one of four outcomes, and the placement history follows it in the
same transaction (a change of employer or to self-employment starts a new episode linked to the
earlier one; leaving ends the running one with the reason). A reason and date are required when
the youth left; "Other" needs an explanation. The eight employment types and eight reasons are
the approved lists. A salary and its band are grant-only economic data, refused on
self-employment, and never written to the audit trail."""

from datetime import timedelta
from decimal import Decimal

import pytest

from apps.audit.models import AuditEvent
from apps.configuration.models import EmploymentType, LeavingReason, SalaryBand
from apps.placements.models import FollowUp, Placement

from .test_followups import (  # noqa: F401
    FU,
    JSON,
    PL,
    client_for,
    enrollment,
    first_open,
    officer,
    place,
    today,
    youth,
)
from .test_participants import world  # noqa: F401
from .test_self_employment import give_income_grant

START = 100  # days ago: the 90-day check-in is due and open


def kind(code):
    return str(EmploymentType.objects.get(code=code).pk)


def reason(code):
    return str(LeavingReason.objects.get(code=code).pk)


def ago(days):
    return (today() - timedelta(days=days)).isoformat()


@pytest.fixture
def band(db):
    return SalaryBand.objects.create(
        code="B1", name="KES 10,000 to 19,999", name_normalised="kes 10000 to 19999",
        min_amount=Decimal("10000"), max_amount=Decimal("19999.99"),
    )  # fmt: skip


@pytest.fixture
def started(officer, youth, enrollment):  # noqa: F811
    c = client_for(officer)
    pid = place(c, youth, start=today() - timedelta(days=START))
    return c, pid, first_open(c, placement=pid)["id"]


def complete(c, fid, **body):
    return c.post(
        f"{FU}/{fid}/complete", {"evidence_source": "phone_call", **body}, content_type=JSON
    )


def error(r):
    assert r.status_code == 409, r.content
    return r.json()["errors"][0]


# --- the approved lists ---------------------------------------------------------------------------


def test_the_approved_types_and_reasons_are_seeded(db):
    assert list(EmploymentType.objects.order_by("name").values_list("name", flat=True)) == sorted([
        "Permanent employment", "Contract employment", "Temporary employment",
        "Casual employment", "Internship", "Apprenticeship", "Self-employment", "Other",
    ])  # fmt: skip
    assert EmploymentType.objects.get(self_employment=True).code == "SELF"
    assert LeavingReason.objects.count() == 8
    assert list(LeavingReason.objects.filter(needs_note=True).values_list("code", flat=True)) == [
        "OTHER"
    ]
    assert SalaryBand.objects.count() == 0  # CAP-YEI has not given the ranges


def test_the_options_carry_the_lists(started):
    c, _, _ = started
    fo = c.get(f"{FU}/options").json()
    assert [o["value"] for o in fo["outcomes"]] == [
        "same_employer", "changed_employer", "self_employed", "left_employment",
    ]  # fmt: skip
    assert len(fo["leaving_reasons"]) == 8
    po = c.get(f"{PL}/options").json()
    assert len(po["employment_types"]) == 8 and po["salary_bands"] == []


# --- outcomes -------------------------------------------------------------------------------------


def test_same_employer_keeps_the_placement_running(started):
    c, pid, fid = started
    r = complete(c, fid, outcome="same_employer")
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["outcome"] == "same_employer" and d["still_employed"] is True
    assert d["outcome_label"] == "Still with the same employer"
    assert Placement.objects.get(pk=pid).end_date is None


def test_same_employer_with_a_leaving_reason_is_refused(started):
    c, _, fid = started
    e = error(complete(c, fid, outcome="same_employer", leaving_reason_id=reason("RESIGNED")))
    assert e["code"] == "not_left"


def test_left_employment_needs_a_reason_and_date_and_ends_the_placement(started):
    c, pid, fid = started
    assert error(complete(c, fid, outcome="left_employment"))["field"] == "leaving_reason_id"
    e = error(complete(c, fid, outcome="left_employment", leaving_reason_id=reason("RESIGNED")))
    assert e["field"] == "left_on"
    r = complete(
        c, fid, outcome="left_employment", leaving_reason_id=reason("RESIGNED"), left_on=ago(5)
    )
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["still_employed"] is False and d["leaving_reason"] == "Resigned voluntarily"
    p = Placement.objects.get(pk=pid)
    assert p.end_date.isoformat() == ago(5) and p.exit_reason == "Resigned voluntarily"


def test_other_reason_needs_an_explanation(started):
    c, _, fid = started
    body = {"outcome": "left_employment", "leaving_reason_id": reason("OTHER"), "left_on": ago(5)}
    assert error(complete(c, fid, **body))["field"] == "observations"
    r = complete(c, fid, **body, observations="Moved to care for a relative")
    assert r.status_code == 200, r.content


@pytest.mark.parametrize(
    "left_on,code", [(lambda: ago(-1), "future"), (lambda: ago(START + 1), "before_start")]
)
def test_the_leaving_date_must_be_inside_the_placement(started, left_on, code):
    c, _, fid = started
    r = complete(
        c, fid, outcome="left_employment", leaving_reason_id=reason("RESIGNED"), left_on=left_on()
    )
    assert error(r)["code"] == code


def test_a_retired_reason_is_refused(started):
    c, _, fid = started
    LeavingReason.objects.filter(code="PERSONAL").update(active=False)
    r = complete(
        c, fid, outcome="left_employment", leaving_reason_id=reason("PERSONAL"), left_on=ago(5)
    )
    assert error(r)["code"] == "unknown_reason"


def test_changed_employer_starts_a_linked_episode(started):
    c, pid, fid = started
    assert error(complete(c, fid, outcome="changed_employer"))["field"] == "new_job"
    job = {"start_date": ago(3), "employer_name_source": "Beta Ltd", "designation": "Clerk",
           "employment_type_id": kind("CONTRACT")}  # fmt: skip
    assert error(complete(c, fid, outcome="changed_employer", new_job=job))["field"] == "left_on"
    r = complete(
        c, fid, outcome="changed_employer", left_on=ago(4), new_job=job,
        leaving_reason_id=reason("OTHER-OPPORTUNITY"),
    )  # fmt: skip
    assert r.status_code == 200, r.content
    d = r.json()
    old, new = Placement.objects.get(pk=pid), Placement.objects.get(pk=d["new_placement_id"])
    assert old.end_date.isoformat() == ago(4) and old.exit_reason
    assert new.end_date is None and new.previous_placement_id == old.pk
    assert new.pathway == "wage" and str(new.employment_type_id) == kind("CONTRACT")
    assert d["still_employed"] is True


def test_a_failed_change_leaves_everything_as_it_was(started):
    """The follow-up, the old placement and the placement count all roll back together."""
    c, pid, fid = started
    before = Placement.objects.count()
    bad = {"start_date": ago(3), "employer_name_source": "Beta Ltd", "designation": "Clerk",
           "employment_type_id": "00000000-0000-0000-0000-000000000000"}  # fmt: skip
    r = complete(
        c, fid, outcome="changed_employer", left_on=ago(4), new_job=bad,
        leaving_reason_id=reason("OTHER-OPPORTUNITY"),
    )  # fmt: skip
    assert r.status_code in (400, 409), r.content
    assert Placement.objects.count() == before
    assert Placement.objects.get(pk=pid).end_date is None
    assert FollowUp.objects.get(pk=fid).status == FollowUp.OPEN


def test_self_employment_is_its_own_outcome(started):
    c, _, fid = started
    job = {"start_date": ago(3), "employer_name_source": "Own kiosk", "pathway": "self_employment"}
    e = error(complete(c, fid, outcome="changed_employer", left_on=ago(4), new_job=job))
    assert e["code"] == "self_employment"
    job.pop("pathway")
    r = complete(
        c, fid, outcome="self_employed", left_on=ago(4),
        new_job={**job, "business_activity": "Phone repairs", "employment_type_id": kind("SELF")},
    )  # fmt: skip
    assert r.status_code == 200, r.content
    new = Placement.objects.get(pk=r.json()["new_placement_id"])
    assert new.pathway == "self_employment" and new.business_activity == "Phone repairs"


def test_a_new_job_already_recorded_is_linked_not_doubled(started, officer, youth):  # noqa: F811
    c, pid, fid = started
    c.post(f"{PL}/{pid}/change-employer", {
        "end_date": ago(10), "start_date": ago(9), "pathway": "wage",
        "employer_name_source": "Gamma",
    }, content_type=JSON)  # fmt: skip
    running = Placement.objects.get(end_date__isnull=True, status="placed")
    before = Placement.objects.count()
    r = complete(c, fid, outcome="changed_employer")
    assert r.status_code == 200, r.content
    assert r.json()["new_placement_id"] == str(running.pk)
    assert Placement.objects.count() == before
    assert running.previous_placement_id is not None


def test_same_employer_is_refused_once_the_placement_ended(started):
    c, pid, fid = started
    c.post(f"{PL}/{pid}/end", {"end_date": ago(2)}, content_type=JSON)
    assert error(complete(c, fid, outcome="same_employer"))["code"] == "not_running"


def test_the_old_form_still_records_without_touching_placements(started):
    c, pid, fid = started
    r = complete(c, fid, still_employed=False)
    assert r.status_code == 200, r.content
    f = FollowUp.objects.get(pk=fid)
    assert f.outcome == "" and f.still_employed is False
    assert Placement.objects.get(pk=pid).end_date is None


def test_observations_stay_out_of_the_audit_trail(started):
    c, _, fid = started
    complete(c, fid, outcome="same_employer", observations="Synthetic private remark")
    ev = AuditEvent.objects.filter(action="followup.completed").last()
    assert ev.after["outcome"] == "same_employer"
    assert "Synthetic private remark" not in str(ev.before) + str(ev.after)


# --- employment type and salary -------------------------------------------------------------------


def test_the_type_must_match_the_pathway(officer, youth, enrollment):  # noqa: F811
    c = client_for(officer)
    body = {"participant_id": str(youth.pk), "pathway": "wage", "start_date": ago(1),
            "employer_name_source": "Acme", "employment_type_id": kind("SELF")}  # fmt: skip
    r = c.post(PL, body, content_type=JSON)
    assert r.status_code == 409 and "Self-employment" in r.json()["errors"][0]["message"]
    r = c.post(PL, {**body, "employment_type_id": kind("INTERNSHIP")}, content_type=JSON)
    assert r.status_code == 201, r.content
    assert c.get(f"{PL}/{r.json()['id']}").json()["employment_type"] == "Internship"


def test_salary_needs_the_grant_and_finds_its_band(officer, youth, enrollment, band, make_user):  # noqa: F811
    c = client_for(officer)
    body = {"participant_id": str(youth.pk), "pathway": "wage", "start_date": ago(1),
            "employer_name_source": "Acme", "salary_amount": "15000.00"}  # fmt: skip
    r = c.post(PL, body, content_type=JSON)
    assert r.status_code == 409 and r.json()["errors"][0]["field"] == "salary_amount"
    give_income_grant(officer, make_user)
    r = c.post(PL, body, content_type=JSON)
    assert r.status_code == 201, r.content
    d = c.get(f"{PL}/{r.json()['id']}").json()
    assert d["salary_amount"] == "15000.00" and d["salary_band_id"] == str(band.pk)
    ev = AuditEvent.objects.filter(action="placement.recorded").last() or AuditEvent.objects.last()
    assert "15000" not in str(ev.after)


def test_without_the_grant_salary_is_hidden(officer, youth, enrollment, band, make_user):  # noqa: F811
    c = client_for(officer)
    give_income_grant(officer, make_user)
    pid = place(c, youth, salary_amount="15000.00")
    other = make_user("reader", "Placement officer")
    from apps.identity import services as identity

    identity.set_scopes(actor=None, user=other, scopes=[("officer", str(officer.pk))])
    d = client_for(other).get(f"{PL}/{pid}").json()
    assert d["salary_amount"] is None and d["salary_band_id"] is None and d["salary_band"] == ""


def test_salary_outside_the_band_or_on_self_employment_is_refused(
    officer, youth, enrollment, band, make_user,  # noqa: F811
):  # fmt: skip
    c = client_for(officer)
    give_income_grant(officer, make_user)
    body = {"participant_id": str(youth.pk), "pathway": "wage", "start_date": ago(1),
            "employer_name_source": "Acme"}  # fmt: skip
    r = c.post(PL, {**body, "salary_amount": "25000", "salary_band_id": str(band.pk)},
               content_type=JSON)  # fmt: skip
    assert r.status_code == 409 and "outside the band" in r.json()["errors"][0]["message"]
    r = c.post(PL, {**body, "pathway": "self_employment", "salary_amount": "5000"},
               content_type=JSON)  # fmt: skip
    assert r.status_code == 409 and "business income" in r.json()["errors"][0]["message"]
    r = c.post(PL, {**body, "salary_band_id": str(band.pk)}, content_type=JSON)
    assert r.status_code == 201, r.content  # a band alone is enough


def test_a_band_cannot_be_upside_down(db):
    from django.core.exceptions import ValidationError

    b = SalaryBand(code="X", name="X", min_amount=Decimal("5"), max_amount=Decimal("1"))
    with pytest.raises(ValidationError):
        b.clean()
