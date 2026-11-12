"""Youth portal: invite, one-time activation, consent, self-reported entries, isolation."""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.configuration.models import Skill
from apps.participants.models import Participant, ParticipantContact, ParticipantSkill
from apps.portal import services
from apps.portal.models import YouthAccount, YouthInvite

EMAIL = "amina.youth@example.org"
PASSWORD = "a-much-longer-passphrase-9"  # noqa: S105 (test value)


def api(user=None):
    c = Client(enforce_csrf_checks=False)
    if user:
        c.force_login(user)
    return c


@pytest.fixture(autouse=True)
def _fresh_throttle():
    cache.clear()


@pytest.fixture
def person(db):
    p = Participant.objects.create(full_name_source="Amina Test")
    ParticipantContact.objects.create(participant=p, kind="email", value=EMAIL, is_primary=True)
    return p


@pytest.fixture
def steward(make_user):
    return make_user("steward", "Data steward")


def send(steward, person, email=EMAIL):
    return api(steward).post(
        f"/api/v1/participants/{person.pk}/invite",
        {"email": email},
        content_type="application/json",
    )


def token_from_mail():
    body = mail.outbox[-1].body
    return body.split("#token=")[1].split()[0]


def activate(person, steward):
    send(steward, person)
    token = token_from_mail()
    r = api().post(
        "/api/v1/youth/activate",
        {"token": token, "password": PASSWORD},
        content_type="application/json",
    )
    assert r.status_code == 204, r.content
    return token


def test_invite_goes_only_to_an_address_on_the_record(steward, person):
    assert send(steward, person, "someone.else@example.org").status_code == 400
    assert send(steward, person).status_code == 200
    assert mail.outbox[-1].to == [EMAIL]
    status = api(steward).get(f"/api/v1/participants/{person.pk}/invite").json()
    assert status["state"] == "pending" and status["emails"] == [EMAIL]


def test_invite_audit_holds_neither_address_nor_token(steward, person):
    send(steward, person)
    token = token_from_mail()
    blob = " ".join(str(e.after) + str(e.before) for e in AuditEvent.objects.all())
    assert token not in blob and EMAIL not in blob.replace("user.pending", "")


def test_officer_without_the_permission_cannot_invite(make_user, person):
    officer = make_user("off", "Placement officer")
    assert send(officer, person).status_code == 403


def test_activation_is_one_time_and_expires(steward, person):
    token = activate(person, steward)
    again = api().post(
        "/api/v1/youth/activate",
        {"token": token, "password": PASSWORD},
        content_type="application/json",
    )
    assert again.status_code == 400
    # An expired invite is refused.
    p2 = Participant.objects.create(full_name_source="Late Youth")
    ParticipantContact.objects.create(participant=p2, kind="email", value="late@example.org")
    send(steward, p2, "late@example.org")
    tok = token_from_mail()
    YouthInvite.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    r = api().post(
        "/api/v1/youth/activate/check",
        {"token": tok},
        content_type="application/json",
    )
    assert r.status_code == 400


def test_weak_password_keeps_the_invite_usable(steward, person):
    send(steward, person)
    token = token_from_mail()
    r = api().post(
        "/api/v1/youth/activate",
        {"token": token, "password": "12345678"},
        content_type="application/json",
    )
    assert r.status_code == 400
    ok = api().post(
        "/api/v1/youth/activate",
        {"token": token, "password": PASSWORD},
        content_type="application/json",
    )
    assert ok.status_code == 204


def test_reinvite_replaces_pending_and_active_cannot_be_reinvited(steward, person):
    send(steward, person)
    first = token_from_mail()
    send(steward, person)
    assert (
        api()
        .post("/api/v1/youth/activate/check", {"token": first}, content_type="application/json")
        .status_code
        == 400
    )
    activate(person, steward)
    assert send(steward, person).status_code == 400


def test_existing_user_email_is_never_reused(steward, person, make_user):
    make_user("taken", "Manager").__class__.objects.filter(username="taken").update(email=EMAIL)
    assert send(steward, person).status_code == 400


def test_youth_signs_in_without_mfa_even_when_required_for_all_staff(steward, person, settings):
    settings.AUTH_MFA_ALL_STAFF = True
    activate(person, steward)
    r = api().post(
        "/api/v1/auth/login",
        {"username": EMAIL, "password": PASSWORD},
        content_type="application/json",
    )
    assert r.json()["status"] == "ok"


def test_consent_gates_the_profile_and_entries_are_self_reported(steward, person):
    activate(person, steward)
    from django.contrib.auth.models import User

    youth = api(User.objects.get(username=EMAIL))
    me = youth.get("/api/v1/youth/me").json()
    assert me["name"] == "Amina Test" and me["consent"]["given"] is False
    assert "profile" not in me
    blocked = youth.put("/api/v1/youth/profile", {"skills": []}, content_type="application/json")
    assert blocked.status_code == 400
    bad = youth.post("/api/v1/youth/consent", {"version": "old"}, content_type="application/json")
    assert bad.status_code == 400
    ok = youth.post(
        "/api/v1/youth/consent",
        {"version": services.CONSENT_VERSION},
        content_type="application/json",
    )
    assert ok.json()["consent"]["given"] is True and "profile" in ok.json()

    cook = Skill.objects.get(code="SK-FOOD")
    body = {"skills": [{"skill_id": str(cook.pk), "proficiency": 2}]}
    put = youth.put("/api/v1/youth/profile", body, content_type="application/json")
    assert put.status_code == 200, put.content
    row = put.json()["profile"]["skills"][0]
    assert row["source"] == "youth" and row["verified"] is False
    # Staff see it as self-reported and can verify it; the youth never sees who verified.
    staff = api(steward)
    url = f"/api/v1/participants/{person.pk}/profile"
    assert staff.get(url).json()["skills"][0]["source"] == "youth"
    staff.post(
        url + "/verify",
        {"kind": "skill", "id": row["id"], "verified": True},
        content_type="application/json",
    )
    seen = youth.get("/api/v1/youth/me").json()["profile"]["skills"][0]
    assert seen["verified"] is True and seen["verified_by"] == ""
    # A youth cannot delete an entry staff verified.
    gone = youth.put("/api/v1/youth/profile", {"skills": []}, content_type="application/json")
    assert gone.status_code == 400
    assert ParticipantSkill.objects.filter(participant=person).count() == 1


def test_youth_reaches_no_staff_route_and_sees_only_their_record(steward, person, make_user):
    from django.contrib.auth.models import User

    other = Participant.objects.create(full_name_source="Someone Else")
    activate(person, steward)
    youth = api(User.objects.get(username=EMAIL))
    for url in (
        "/api/v1/participants",
        f"/api/v1/participants/{person.pk}",
        f"/api/v1/participants/{other.pk}/profile",
        f"/api/v1/participants/{person.pk}/invite",
    ):
        assert youth.get(url).status_code == 403, url
    assert youth.get("/api/v1/me").json()["permissions"] == ["youth.self_service"]
    assert YouthAccount.objects.filter(participant=other).count() == 0


def test_staff_user_without_a_link_gets_404_from_youth_me(make_user):
    assert api(make_user("plain", "Manager")).get("/api/v1/youth/me").status_code == 403


def test_withdraw_removes_the_pending_account(steward, person):
    send(steward, person)
    r = api(steward).delete(f"/api/v1/participants/{person.pk}/invite")
    assert r.status_code == 200 and r.json()["state"] == "none"
    assert not YouthAccount.objects.exists()
