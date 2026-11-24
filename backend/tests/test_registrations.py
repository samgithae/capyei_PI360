"""Self-registration requests and the steward queue (NEW-044, NEW-072; D-083). Synthetic data."""

import datetime

import pytest
from django.core.cache import cache
from django.test import Client

from apps.audit.models import AuditEvent
from apps.configuration.models import FeatureFlag
from apps.portal import services
from apps.portal.models import RegistrationRequest

URL = "/api/v1/registrations"


def api(user=None):
    c = Client(enforce_csrf_checks=False)
    if user:
        c.force_login(user)
    return c


@pytest.fixture(autouse=True)
def _fresh():
    cache.clear()


@pytest.fixture
def flag_on(db):
    FeatureFlag.objects.update_or_create(key=services.REGISTRATION_FLAG, defaults={"enabled": True})


@pytest.fixture
def steward(make_user):
    return make_user("steward", "Data steward")


@pytest.fixture
def admin(make_user):
    return make_user("admin", "Administrator")


def make(**over):
    args = dict(
        given_name="Test", family_name="Person", date_of_birth=datetime.date(2003, 5, 1),
        email="Test.Person@Example.org", phone="+254 700 000 001", ip="203.0.113.9",
        consent_version="draft",
    )  # fmt: skip
    args.update(over)
    return services.start_registration(**args)


def test_only_hashes_are_stored(db):
    req, token, otp = make()
    req.refresh_from_db()
    assert req.email == "test.person@example.org" and req.phone == "+254700000001"
    assert token not in (req.verify_token_hash, req.otp_hash)
    assert otp not in req.otp_hash and len(req.verify_token_hash) == 64
    assert "203.0.113.9" not in req.ip_hash and len(req.ip_hash) == 64
    assert req.status == RegistrationRequest.PENDING


def test_needs_an_email_or_a_phone(db):
    with pytest.raises(services.RegistrationFailure):
        make(email="", phone="")


def test_queue_is_not_found_while_the_flag_is_off(steward, db):
    make()
    assert api(steward).get(URL).status_code == 404


def test_queue_lists_filters_and_counts(steward, flag_on):
    make()
    make(given_name="Other", email="o@example.org", phone="")
    body = api(steward).get(URL).json()
    assert body["total"] == 2 and body["counts"] == {"pending_verification": 2}
    assert api(steward).get(URL + "?search=other").json()["total"] == 1
    assert api(steward).get(URL + "?status=rejected").json()["total"] == 0
    assert "verify_token_hash" not in body["results"][0]


def test_reject_needs_a_reason_and_is_audited(steward, flag_on):
    req, _, _ = make()
    bad = api(steward).post(
        f"{URL}/{req.pk}/reject", {"reason": " "}, content_type="application/json"
    )
    assert bad.status_code == 400
    ok = api(steward).post(
        f"{URL}/{req.pk}/reject", {"reason": "Not a CAP-YEI youth"}, content_type="application/json"
    )
    assert ok.status_code == 200 and ok.json()["status"] == "rejected"
    assert AuditEvent.objects.filter(action="registration.rejected").count() == 1


def test_only_rejected_requests_can_be_deleted_by_an_administrator(steward, admin, flag_on):
    req, _, _ = make()
    assert api(steward).delete(f"{URL}/{req.pk}").status_code == 403
    assert api(admin).delete(f"{URL}/{req.pk}").status_code == 400  # still pending
    api(steward).post(
        f"{URL}/{req.pk}/reject", {"reason": "Duplicate"}, content_type="application/json"
    )
    assert api(admin).delete(f"{URL}/{req.pk}").status_code == 204
    assert not RegistrationRequest.objects.filter(pk=req.pk).exists()
    assert AuditEvent.objects.filter(action="registration.deleted").count() == 1


# --- public sign-up (NEW-045) ---------------------------------------------------------------

from django.core import mail  # noqa: E402

SUBMIT, VERIFY = URL + "/submit", URL + "/verify"
FORM = {
    "given_name": "Test", "family_name": "Person", "date_of_birth": "2003-05-01",
    "email": "test.person@example.org", "phone": "0700 000 001", "consent": True,
}  # fmt: skip


def submit(**over):
    return api().post(SUBMIT, {**FORM, **over}, content_type="application/json")


def token_from_mail():
    return mail.outbox[-1].body.split("#token=")[1].split()[0]


def test_signup_is_not_found_while_the_flag_is_off(db):
    assert submit().status_code == 404
    assert api().post(VERIFY, {"token": "x"}, content_type="application/json").status_code == 404


def test_signup_then_verify(flag_on):
    r = submit()
    assert r.status_code == 202 and len(mail.outbox) == 1
    req = RegistrationRequest.objects.get()
    assert req.status == "pending_verification" and req.phone == "0700000001"
    token = token_from_mail()
    ok = api().post(VERIFY, {"token": token}, content_type="application/json")
    assert ok.status_code == 204
    req.refresh_from_db()
    assert req.status == "verified" and req.email_verified_at and not req.verify_token_hash
    again = api().post(VERIFY, {"token": token}, content_type="application/json")
    assert again.status_code == 400  # single use


def test_bad_and_expired_links_get_the_same_answer(flag_on):
    submit()
    RegistrationRequest.objects.update(
        verify_expires_at=datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
    )
    expired = api().post(VERIFY, {"token": token_from_mail()}, content_type="application/json")
    wrong = api().post(VERIFY, {"token": "nonsense"}, content_type="application/json")
    assert expired.status_code == wrong.status_code == 400
    strip = lambda r: {k: v for k, v in r.json().items() if k != "request_id"}  # noqa: E731
    assert strip(expired) == strip(wrong)


def test_replies_do_not_reveal_whether_someone_is_known(flag_on):
    fresh = submit()
    repeat = submit()  # same e-mail again
    api().post(VERIFY, {"token": token_from_mail()}, content_type="application/json")
    after_verify = submit()  # now settled: nothing more is sent
    sent = len(mail.outbox)
    assert fresh.status_code == repeat.status_code == after_verify.status_code == 202
    assert fresh.json() == repeat.json() == after_verify.json()
    assert RegistrationRequest.objects.count() == 1
    assert sent == 2  # first mail, plus a fresh link for the repeat; none after verification


def test_a_lost_mail_gets_a_new_link_that_works(flag_on):
    submit()
    first = token_from_mail()
    submit()
    second = token_from_mail()
    assert first != second
    old = api().post(VERIFY, {"token": first}, content_type="application/json")
    assert old.status_code == 400
    assert api().post(VERIFY, {"token": second}, content_type="application/json").status_code == 204


def test_consent_is_required_and_the_contact_is_rate_limited(flag_on):
    assert submit(consent=False).status_code == 400
    for _ in range(services.REGISTER_PER_CONTACT + 2):
        submit()
    assert len(mail.outbox) == services.REGISTER_PER_CONTACT


def test_the_ip_is_rate_limited(flag_on, settings):
    from rest_framework.throttling import ScopedRateThrottle

    ScopedRateThrottle.THROTTLE_RATES = {**ScopedRateThrottle.THROTTLE_RATES, "register": "3/hour"}
    try:
        codes = [submit(email=f"p{i}@example.org").status_code for i in range(5)]
    finally:
        ScopedRateThrottle.THROTTLE_RATES["register"] = "10/hour"
    assert codes[:3] == [202, 202, 202] and codes[3] == 429


# --- NEW-046: officer review (link or create) ---------------------------------------------


def verified(**over):
    req, _t, _o = make(**over)
    req.status = RegistrationRequest.VERIFIED
    req.email_verified_at = datetime.datetime.now(datetime.UTC)
    req.save()
    return req


def existing(name="Test Person"):
    from apps.participants.models import Participant

    return Participant.objects.create(full_name_source=name)


def test_matches_show_similar_people_and_mark_the_request(steward, flag_on):
    req = verified()
    existing("Test Person")
    r = api(steward).get(f"{URL}/{req.pk}/matches")
    assert r.status_code == 200 and len(r.json()["matches"]) == 1
    req.refresh_from_db()
    assert req.possible_duplicate


def test_link_never_creates_a_person(steward, flag_on):
    from apps.participants.models import Participant

    req, p = verified(), existing()
    before = Participant.objects.count()
    bad = api(steward).post(f"{URL}/{req.pk}/link", {"participant_id": str(p.pk)})
    assert bad.status_code == 400  # a reason is required
    r = api(steward).post(
        f"{URL}/{req.pk}/link", {"participant_id": str(p.pk), "reason": "Same person"}
    )
    assert r.status_code == 200
    req.refresh_from_db()
    assert req.status == RegistrationRequest.LINKED and req.participant_id == p.pk
    assert Participant.objects.count() == before
    assert AuditEvent.objects.filter(action="registration.linked").exists()


def test_two_sign_ups_cannot_link_to_one_record(steward, flag_on):
    p = existing()
    a, b = verified(), verified(email="b@example.org")
    body = {"participant_id": str(p.pk), "reason": "Same person"}
    assert api(steward).post(f"{URL}/{a.pk}/link", body).status_code == 200
    assert api(steward).post(f"{URL}/{b.pk}/link", body).status_code == 400


def test_create_warns_when_someone_similar_exists(steward, flag_on):
    from apps.participants.models import Participant

    existing("Test Person")
    req = verified()
    body = {"reason": "Different person, checked"}
    warn = api(steward).post(f"{URL}/{req.pk}/create", body)
    assert warn.status_code == 400 and "confirm_similar" in str(warn.json())
    ok = api(steward).post(f"{URL}/{req.pk}/create", {**body, "confirm_similar": True})
    assert ok.status_code == 200
    req.refresh_from_db()
    assert req.status == RegistrationRequest.APPROVED
    new = Participant.objects.get(pk=req.participant_id)
    assert new.given_name == "Test" and new.date_of_birth == req.date_of_birth


def test_create_with_nobody_similar_needs_no_confirmation(steward, flag_on):
    req = verified(given_name="Zanele", family_name="Qwerty")
    r = api(steward).post(f"{URL}/{req.pk}/create", {"reason": "New youth"})
    assert r.status_code == 200


def test_unverified_or_settled_requests_cannot_be_decided(steward, flag_on):
    pending, _t, _o = make()
    r = api(steward).post(f"{URL}/{pending.pk}/create", {"reason": "x"})
    assert r.status_code == 400
    done = verified(email="c@example.org")
    assert api(steward).post(f"{URL}/{done.pk}/create", {"reason": "ok"}).status_code == 200
    assert api(steward).post(f"{URL}/{done.pk}/create", {"reason": "again"}).status_code == 400


# --- NEW-047: the invite goes out when a sign-up is approved or linked ---------------------


def test_creating_a_new_record_sends_one_invite_to_the_confirmed_address(steward, flag_on):
    from django.core import mail

    from apps.portal.models import YouthAccount

    req = verified(given_name="Zanele", family_name="Qwerty")
    r = api(steward).post(f"{URL}/{req.pk}/create", {"reason": "New youth"})
    assert r.json()["invite"] == {"sent": True, "reason": ""}
    req.refresh_from_db()
    assert YouthAccount.objects.filter(participant_id=req.participant_id).count() == 1
    assert [m.to for m in mail.outbox if "invitation" in m.subject] == [["test.person@example.org"]]
    assert AuditEvent.objects.filter(action="youth.invited").exists()


def test_linking_invites_the_youth_unless_they_already_have_an_account(steward, flag_on):
    from django.core import mail

    from apps.portal.models import YouthAccount

    p = existing()
    req = verified()
    body = {"participant_id": str(p.pk), "reason": "Same person"}
    assert api(steward).post(f"{URL}/{req.pk}/link", body).json()["invite"]["sent"] is True
    assert YouthAccount.objects.filter(participant=p).count() == 1
    assert [m.to for m in mail.outbox if "invitation" in m.subject] == [["test.person@example.org"]]


def test_an_active_account_blocks_the_invite_but_not_the_decision(steward, flag_on):
    from django.core import mail

    from apps.portal.models import YouthAccount

    p = existing()
    first = verified()
    api(steward).post(f"{URL}/{first.pk}/link", {"participant_id": str(p.pk), "reason": "Same"})
    acct = YouthAccount.objects.get(participant=p)
    acct.user.is_active = True
    acct.user.save()
    mail.outbox.clear()
    first.refresh_from_db()
    out = services.invite_registrant(actor=steward, req=first)
    assert out == {"sent": False, "reason": "already_has_account"}
    assert mail.outbox == [] and YouthAccount.objects.filter(participant=p).count() == 1


def test_no_invite_for_an_unverified_address_or_an_undecided_request(steward, flag_on):
    pending, _t, _o = make()
    assert services.invite_registrant(actor=steward, req=pending)["reason"] == "not_decided"
    req = verified(email="d@example.org")
    api(steward).post(f"{URL}/{req.pk}/create", {"reason": "ok"})
    req.refresh_from_db()
    req.email_verified_at = None
    assert services.invite_registrant(actor=steward, req=req)["reason"] == "unverified_email"


def test_a_failed_mail_keeps_the_decision(steward, flag_on, monkeypatch):
    from django.core import mail

    def boom(*a, **k):
        raise OSError("mail down")

    monkeypatch.setattr(mail, "send_mail", boom)
    req = verified(email="e@example.org")
    r = api(steward).post(f"{URL}/{req.pk}/create", {"reason": "ok"})
    assert r.status_code == 200 and r.json()["invite"]["reason"] == "mail_failed"
    req.refresh_from_db()
    assert req.status == RegistrationRequest.APPROVED
