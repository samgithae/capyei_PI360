"""Merging two records of one youth with conflicts (PI360-NEW-077, D-081/B28).

Gaps are filled from the other record; real differences wait for the steward's choice. A
critical conflict (two running placements, the same course offering, two active referrals to one
opportunity, two portal accounts) saves the merge as pending resolution and moves nothing. A
placement is never closed, deleted or overwritten on its own: an authorised officer ends one,
or marks one as the same placement recorded twice, with a reason. All data here is synthetic."""

from datetime import date

import pytest
from django.test import Client

from apps.audit.models import AuditEvent
from apps.employers.models import Employer, Opportunity
from apps.participants import services
from apps.participants.models import (
    DuplicateCandidate,
    MergeResolution,
    Participant,
    ParticipantMerge,
)
from apps.placements import services as placements
from apps.placements.models import Placement
from apps.portal.models import YouthAccount
from apps.referrals.models import Referral

from .test_duplicates import URL, base, person  # noqa: F401

JSON = "application/json"


@pytest.fixture
def pair(base):  # noqa: F811
    a = person(base, "Test Youth", phone="0700000101", no="S1", gender="female")
    b = person(base, "Test Youth", phone="0700000101", cc=1, no="S2", age_at_source=22)
    services.scan()
    return a, b, DuplicateCandidate.objects.get()


def running(youth, employer="Test Bakery", start=date(2026, 1, 5)):
    return placements.record(
        actor=None, enrollment_id=youth.enrollments.get().pk, source_status="Employment",
        pathway="wage", status="placed", employer_name_source=employer, start_date=start,
    )  # fmt: skip


def client(user):
    c = Client()
    c.force_login(user)
    return c


def test_gaps_are_filled_and_real_differences_need_a_choice(pair, make_user):
    a, b, cand = pair
    b.gender = "male"
    b.save()
    fields = {f["field"]: f for f in services.review(candidate=cand, survivor_id=a.pk)["fields"]}
    assert fields["age_at_source"]["keep"] == "merged"  # the survivor has no age: filled
    assert fields["gender"]["conflict"] and fields["gender"]["keep"] is None
    with pytest.raises(services.DuplicateFailure) as exc:
        services.merge(actor=make_user("s", "Data steward"), candidate=cand,
                       survivor_id=a.pk, reason="Same youth")  # fmt: skip
    assert exc.value.field == "fields" and "Gender" in exc.value.message
    rec = services.merge(
        actor=make_user("s2", "Data steward"), candidate=cand, survivor_id=a.pk,
        fields={"gender": "survivor"}, reason="Same youth",
    )  # fmt: skip
    a.refresh_from_db()
    assert (a.gender, a.age_at_source) == ("female", 22)
    assert rec.survivor_id == a.pk


def test_a_lone_running_placement_moves_with_its_enrollment(pair, make_user):
    a, b, cand = pair
    p = running(b)
    services.merge(actor=make_user("s", "Data steward"), candidate=cand, survivor_id=a.pk,
                   reason="Same youth")  # fmt: skip
    p.refresh_from_db()
    assert p.enrollment.participant_id == a.pk and p.end_date is None
    assert Placement.objects.filter(placements.RUNNING, enrollment__participant=a).count() == 1


def test_two_running_placements_hold_the_merge_and_move_nothing(pair, make_user):
    a, b, cand = pair
    running(a), running(b, employer="Other Shop")
    held = services.merge(actor=make_user("s", "Data steward"), candidate=cand,
                          survivor_id=a.pk, reason="Same youth")  # fmt: skip
    assert held.status == DuplicateCandidate.PENDING
    two = next(c for c in held.conflicts if c["code"] == "two_running_placements")
    assert two["actions"] == ["end", "same"] and two["looks_same"] is False
    assert len(two["items"]) == 2 and "employer" in two["items"][0]
    b.refresh_from_db()
    assert b.merged_into_id is None and b.enrollments.count() == 1
    assert not ParticipantMerge.objects.exists()
    assert AuditEvent.objects.filter(action="duplicate.merge_pending").exists()


def test_same_placement_recorded_twice_is_reconciled_then_completed(pair, make_user):
    a, b, cand = pair
    keep, extra = running(a), running(b)
    steward = make_user("s", "Data steward")
    c = client(steward)
    r = c.post(f"{URL}/duplicates/{cand.pk}/merge",
               {"survivor": str(a.pk), "reason": "Same youth"}, content_type=JSON)  # fmt: skip
    assert r.status_code == 202 and r.json()["status"] == "pending"
    assert r.json()["conflicts"][0]["looks_same"] is True
    early = c.post(f"{URL}/duplicates/{cand.pk}/complete", content_type=JSON)
    assert early.status_code == 409 and early.json()["errors"][0]["field"] == "conflicts"

    r = c.post(f"{URL}/duplicates/{cand.pk}/resolve", {
        "action": "same", "placement_id": str(extra.pk), "keep_id": str(keep.pk),
        "reason": "One job, captured twice",
    }, content_type=JSON)  # fmt: skip
    assert r.status_code == 201, r.content
    extra.refresh_from_db()
    assert extra.status == "recorded_twice" and extra.duplicate_of_id == keep.pk
    assert Placement.objects.filter(pk=extra.pk).exists()  # never deleted

    done = c.post(f"{URL}/duplicates/{cand.pk}/complete", content_type=JSON)
    assert done.status_code == 200, done.content
    assert done.json()["resolutions"][0]["action"] == "same"
    assert Placement.objects.filter(placements.RUNNING, enrollment__participant=a).count() == 1
    res = MergeResolution.objects.get()
    assert (res.decided_by, res.reason) == (steward, "One job, captured twice")


def test_different_placements_need_one_ended_by_the_officer(pair, make_user):
    a, b, cand = pair
    running(a), (old := running(b, employer="Other Shop", start=date(2025, 6, 1)))
    steward = make_user("s", "Data steward")
    services.merge(actor=steward, candidate=cand, survivor_id=a.pk, reason="Same youth")
    c = client(steward)
    no_date = c.post(f"{URL}/duplicates/{cand.pk}/resolve", {
        "action": "end", "placement_id": str(old.pk), "reason": "Left in December",
    }, content_type=JSON)  # fmt: skip
    assert no_date.status_code == 409
    r = c.post(f"{URL}/duplicates/{cand.pk}/resolve", {
        "action": "end", "placement_id": str(old.pk), "end_date": "2025-12-31",
        "reason": "Left in December",
    }, content_type=JSON)  # fmt: skip
    assert r.status_code == 201, r.content
    old.refresh_from_db()
    assert old.end_date == date(2025, 12, 31) and old.status == "placed"
    assert c.post(f"{URL}/duplicates/{cand.pk}/complete", content_type=JSON).status_code == 200


def test_resolution_refuses_placements_outside_the_pair(pair, base, make_user):  # noqa: F811
    a, b, cand = pair
    running(a), running(b)
    stranger = running(person(base, "Someone Else", no="S9"))
    services.merge(actor=make_user("s", "Data steward"), candidate=cand, survivor_id=a.pk,
                   reason="Same youth")  # fmt: skip
    r = client(make_user("s2", "Data steward")).post(f"{URL}/duplicates/{cand.pk}/resolve", {
        "action": "end", "placement_id": str(stranger.pk), "end_date": "2026-02-01",
        "reason": "x",
    }, content_type=JSON)  # fmt: skip
    assert r.status_code == 409
    stranger.refresh_from_db()
    assert stranger.end_date is None


def test_referrals_and_portal_account_move_and_come_back_on_undo(pair, make_user):
    a, b, cand = pair
    opp = Opportunity.objects.create(employer=Employer.objects.create(name="Test Co"),
                                     title="Clerk", status="open")  # fmt: skip
    ref = Referral.objects.create(participant=b, opportunity=opp, stage="submitted")
    acct = YouthAccount.objects.create(user=make_user("youth1"), participant=b)
    user = make_user("s", "Data steward")
    rec = services.merge(actor=user, candidate=cand, survivor_id=a.pk, reason="Same youth")
    ref.refresh_from_db(), acct.refresh_from_db()
    assert ref.participant_id == a.pk and acct.participant_id == a.pk
    services.unmerge(actor=user, merge_record=rec, reason="Mistake")
    ref.refresh_from_db(), acct.refresh_from_db()
    assert ref.participant_id == b.pk and acct.participant_id == b.pk


def test_two_portal_accounts_and_same_referral_are_critical(pair, make_user):
    a, b, cand = pair
    opp = Opportunity.objects.create(employer=Employer.objects.create(name="Test Co"),
                                     title="Clerk", status="open")  # fmt: skip
    for y in (a, b):
        Referral.objects.create(participant=y, opportunity=opp, stage="submitted")
        YouthAccount.objects.create(user=make_user(f"y{y.pk.hex[:6]}"), participant=y)
    codes = {c["code"] for c in services.review(candidate=cand, survivor_id=a.pk)["critical"]}
    assert codes == {"same_opportunity_referral", "two_portal_accounts"}


def test_audit_keeps_both_ids_and_the_merged_record_is_closed(pair, make_user):
    a, b, cand = pair
    services.merge(actor=make_user("s", "Data steward"), candidate=cand, survivor_id=a.pk,
                   reason="Same youth")  # fmt: skip
    on_b = AuditEvent.objects.get(action="participant.merged_into", object_id=str(b.pk))
    assert str(a.pk) in str(on_b.after)
    assert AuditEvent.objects.filter(action="participant.merged", object_id=str(a.pk)).exists()
    b.refresh_from_db()
    assert b.merged_into_id == a.pk and Participant.objects.filter(pk=b.pk).exists()
    cand.refresh_from_db()  # the pair itself is history: both original ids stay on it
    assert {cand.participant_a_id, cand.participant_b_id} == {a.pk, b.pk}
    assert ParticipantMerge.objects.get().absorbed_id == b.pk


def test_pending_merge_can_be_dismissed(pair, make_user):
    a, b, cand = pair
    running(a), running(b)
    user = make_user("s", "Data steward")
    services.merge(actor=user, candidate=cand, survivor_id=a.pk, reason="Same youth")
    services.dismiss(actor=user, candidate=cand, note="Actually two people")
    cand.refresh_from_db()
    assert cand.status == DuplicateCandidate.DISMISSED


def test_only_merge_holders_may_review_resolve_or_complete(pair, make_user):
    a, b, cand = pair
    c = client(make_user("o", "Placement officer"))
    assert c.get(f"{URL}/duplicates/{cand.pk}/review", {"survivor": str(a.pk)}).status_code == 403
    for step in ("resolve", "complete"):
        assert (
            c.post(f"{URL}/duplicates/{cand.pk}/{step}", {}, content_type=JSON).status_code == 403
        )


def test_review_api_shows_fields_and_conflicts(pair, make_user):
    a, b, cand = pair
    running(a), running(b)
    r = client(make_user("s", "Data steward")).get(
        f"{URL}/duplicates/{cand.pk}/review", {"survivor": str(a.pk)}
    )
    assert r.status_code == 200, r.content
    assert r.json()["critical"][0]["code"] == "two_running_placements"
    assert {f["field"] for f in r.json()["fields"]} >= {"gender", "age_at_source"}
