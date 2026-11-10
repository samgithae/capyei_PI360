"""Duplicate detection, merge and unmerge (T-041). Synthetic data only."""

import pytest
from django.test import Client

from apps.audit.models import AuditEvent
from apps.configuration.models import (
    Cohort,
    CohortCourse,
    County,
    Course,
    Programme,
    TrainingInstitution,
)
from apps.participants import services
from apps.participants.models import (
    DuplicateCandidate,
    Participant,
    ParticipantContact,
    ParticipantEnrollment,
    ParticipantMerge,
)

URL = "/api/v1/participants"


@pytest.fixture
def base(db):
    inst = TrainingInstitution.objects.create(
        code="I1", name="College", county=County.objects.get(code="01")
    )
    prog = Programme.objects.create(code="P1", name="Programme 1")
    ccs = []
    for n in ("1", "2"):
        course = Course.objects.create(programme=prog, code=f"C{n}", name=f"Course {n}")
        cohort = Cohort.objects.create(
            programme=prog, institution=inst, code=f"K{n}", name=f"Cohort {n}",
            intake_year=2025, batch_no=int(n), phase="1",
        )  # fmt: skip
        ccs.append(CohortCourse.objects.create(cohort=cohort, course=course))
    return {"inst": inst, "prog": prog, "ccs": ccs}


def person(base, name, *, phone=None, cc=0, no="", **extra):
    p = Participant.objects.create(full_name_source=name, **extra)
    ParticipantEnrollment.objects.create(
        participant=p, cohort_course=base["ccs"][cc], programme=base["prog"],
        institution=base["inst"], source_enrollment_no=no,
    )  # fmt: skip
    if phone:
        ParticipantContact.objects.create(participant=p, kind="phone", value=phone, is_primary=True)
    return p


def steward(make_user):
    c = Client()
    c.force_login(make_user("steward", "Data steward"))
    return c


def test_same_name_and_phone_is_candidate_not_merged(base):
    a = person(base, "Jane Wanjiru", phone="0700 111 222", no="E1")
    b = person(base, "jane  wanjiru", phone="+254700111222", cc=1, no="E2")
    person(base, "Someone Else", phone="0799999999", no="E3")
    result = services.scan()
    assert result["new"] == 1
    cand = DuplicateCandidate.objects.get()
    assert {cand.participant_a_id, cand.participant_b_id} == {a.pk, b.pk}
    assert set(cand.reasons) == {"name_phone", "name_programme"} and cand.score == 0.95
    assert Participant.objects.filter(merged_into__isnull=False).count() == 0  # never auto-merged


def test_scan_is_idempotent_and_respects_dismissal(base, make_user):
    person(base, "Jane Wanjiru", phone="0700111222", no="E1")
    person(base, "Jane Wanjiru", phone="0700111222", cc=1, no="E2")
    services.scan()
    services.scan()
    assert DuplicateCandidate.objects.count() == 1
    cand = DuplicateCandidate.objects.get()
    services.dismiss(actor=make_user("s", "Data steward"), candidate=cand, note="different people")
    services.scan()
    assert DuplicateCandidate.objects.get().status == "dismissed"


def test_same_name_same_programme_different_numbers(base):
    person(base, "Peter Otieno", no="E1")
    person(base, "Peter Otieno", cc=1, no="E2")
    services.scan()
    assert DuplicateCandidate.objects.get().reasons == ["name_programme"]


def test_shared_office_phone_is_ignored(base):
    for i in range(25):
        person(base, f"Zxq{i} Surname{i * 7}", phone="0711000000", no=f"N{i}")
    assert services.scan()["pairs"] == 0


def merge_pair(base, make_user, **kw):
    a = person(base, "Jane Wanjiru", phone="0700111222", no="E1", gender="female", age_at_source=30)
    b = person(base, "Jane Wanjiru", phone="0700111222", cc=1, no="E2", age_at_source=31)
    services.scan()
    cand = DuplicateCandidate.objects.get()
    user = make_user("s", "Data steward")
    survivor = min(a, b, key=lambda p: str(p.pk))
    return a, b, cand, user, survivor


def test_merge_moves_children_and_hides_absorbed(base, make_user):
    a, b, cand, user, survivor = merge_pair(base, make_user)
    other = b if survivor == a else a
    rec = services.merge(
        actor=user, candidate=cand, survivor_id=survivor.pk, fields={"gender": "merged"},
        reason="Same person",
    )  # fmt: skip
    survivor.refresh_from_db()
    other.refresh_from_db()
    assert other.merged_into_id == survivor.pk
    assert survivor.enrollments.count() == 2
    assert survivor.contacts.filter(kind="phone", is_primary=True).count() == 1
    assert survivor.contacts.count() == 2
    assert Participant.objects.visible_to(user).filter(pk=other.pk).count() == 0
    cand.refresh_from_db()
    assert cand.status == "merged"
    assert AuditEvent.objects.filter(action="participant.merged").exists()
    assert rec.reason == "Same person"


def test_unmerge_restores_everything(base, make_user):
    a, b, cand, user, survivor = merge_pair(base, make_user)
    other = b if survivor == a else a
    before = {
        "fields": (survivor.gender, survivor.age_at_source, other.age_at_source),
        "enr": (survivor.enrollments.count(), other.enrollments.count()),
        "contacts": (survivor.contacts.count(), other.contacts.count()),
    }
    rec = services.merge(
        actor=user, candidate=cand, survivor_id=survivor.pk,
        fields={"age_at_source": "merged"}, reason="Same person",
    )  # fmt: skip
    survivor.refresh_from_db()
    assert survivor.age_at_source == other.age_at_source
    services.unmerge(actor=user, merge_record=rec, reason="Mistake")
    survivor.refresh_from_db()
    other.refresh_from_db()
    assert other.merged_into_id is None
    assert (survivor.gender, survivor.age_at_source, other.age_at_source) == before["fields"]
    assert (survivor.enrollments.count(), other.enrollments.count()) == before["enr"]
    assert (survivor.contacts.count(), other.contacts.count()) == before["contacts"]
    assert other.contacts.filter(is_primary=True).count() == 1
    cand.refresh_from_db()
    assert cand.status == "open"
    with pytest.raises(services.DuplicateFailure):
        services.unmerge(actor=user, merge_record=rec, reason="Again")


def test_merge_blocked_when_same_course_offering(base, make_user):
    person(base, "Jane Wanjiru", phone="0700111222", no="E1")
    person(base, "Jane Wanjiru", phone="0700111222", no="E2")  # same cohort course
    services.scan()
    cand = DuplicateCandidate.objects.get()
    with pytest.raises(services.DuplicateFailure) as exc:
        services.merge(
            actor=make_user("s", "Data steward"), candidate=cand,
            survivor_id=cand.participant_a_id, reason="x",
        )  # fmt: skip
    assert exc.value.field == "enrollments"
    assert not ParticipantMerge.objects.exists()


def test_merge_needs_reason_valid_survivor_known_fields(base, make_user):
    a, b, cand, user, survivor = merge_pair(base, make_user)
    for kwargs in (
        {"survivor_id": survivor.pk, "reason": " "},
        {"survivor_id": "00000000-0000-0000-0000-000000000000", "reason": "x"},
        {"survivor_id": survivor.pk, "reason": "x", "fields": {"status": "other"}},
        {"survivor_id": survivor.pk, "reason": "x", "fields": {"id": "merged"}},
    ):
        with pytest.raises(services.DuplicateFailure):
            services.merge(actor=user, candidate=cand, **kwargs)
    assert not ParticipantMerge.objects.exists()


def test_import_style_scan_only_pairs_involving_new_records(base):
    person(base, "Old One", phone="0700000001", no="A")
    person(base, "Old One", phone="0700000001", cc=1, no="B")
    new = person(base, "Fresh Face", phone="0700000009", no="C")
    assert services.scan(only=[new.pk])["pairs"] == 0
    assert services.scan()["pairs"] == 1


# --- API ---------------------------------------------------------------------------------


def test_api_queue_merge_undo_round_trip(base, make_user):
    a, b, cand, user, survivor = merge_pair(base, make_user)
    c = steward(make_user)
    body = c.get(f"{URL}/duplicates").json()
    assert len(body["results"]) == 1
    row = body["results"][0]
    assert row["reasons"][0]["code"] == "name_phone"
    assert row["a"]["phones"]  # a Data steward holds participants.view_contact
    r = c.post(
        f"{URL}/duplicates/{cand.pk}/merge",
        {"survivor": str(survivor.pk), "reason": "Same person"},
        content_type="application/json",
    )
    assert r.status_code == 200, r.content
    merge_id = r.json()["id"]
    assert c.get(f"{URL}/duplicates").json()["results"] == []
    assert len(c.get(f"{URL}/merges").json()["results"]) == 1
    again = c.post(
        f"{URL}/duplicates/{cand.pk}/merge",
        {"survivor": str(survivor.pk), "reason": "x"},
        content_type="application/json",
    )
    assert again.status_code == 409
    undo = c.post(
        f"{URL}/merges/{merge_id}/undo", {"reason": "oops"}, content_type="application/json"
    )
    assert undo.status_code == 200 and undo.json()["undone_at"]
    assert len(c.get(f"{URL}/duplicates").json()["results"]) == 1


def test_api_dismiss_and_scan(base, make_user):
    person(base, "Jane Wanjiru", phone="0700111222", no="E1")
    person(base, "Jane Wanjiru", phone="0700111222", cc=1, no="E2")
    c = steward(make_user)
    assert c.post(f"{URL}/duplicates/scan").json()["new"] == 1
    cand = DuplicateCandidate.objects.get()
    r = c.post(
        f"{URL}/duplicates/{cand.pk}/dismiss", {"reason": "twins"}, content_type="application/json"
    )
    assert r.status_code == 200
    assert c.get(f"{URL}/duplicates").json()["results"] == []
    assert len(c.get(f"{URL}/duplicates", {"status": "dismissed"}).json()["results"]) == 1


def test_merged_record_disappears_from_directory(base, make_user):
    a, b, cand, user, survivor = merge_pair(base, make_user)
    other = b if survivor == a else a
    services.merge(actor=user, candidate=cand, survivor_id=survivor.pk, reason="Same")
    c = steward(make_user)
    assert c.get(URL).json()["total"] == 1
    assert c.get(f"{URL}/{other.pk}").status_code == 404
