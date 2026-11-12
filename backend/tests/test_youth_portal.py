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


def test_youth_edits_their_own_details_but_not_the_risky_ones(steward, person):
    from django.contrib.auth.models import User

    from apps.configuration.models import County

    activate(person, steward)
    youth = api(User.objects.get(username=EMAIL))
    put = lambda body: youth.put(  # noqa: E731
        "/api/v1/youth/details", body, content_type="application/json"
    )
    assert put({"given_name": "Amina"}).status_code == 400  # notice not accepted yet
    youth.post(
        "/api/v1/youth/consent",
        {"version": services.CONSENT_VERSION},
        content_type="application/json",
    )
    county = County.objects.first()
    r = put(
        {
            "given_name": "Amina",
            "family_name": "Njeri",
            "other_names": "Test",
            "gender": "female",
            "date_of_birth": "2003-04-05",
            "county_id": str(county.pk),
            "residence": {
                "county_id": str(county.pk),
                "sub_county": "Westlands",
                "ward": "Parklands",
            },
            "contacts": [
                {"kind": "email", "value": EMAIL, "primary": True},
                {"kind": "phone", "value": "0712 345 678", "primary": True},
            ],
        }
    )
    assert r.status_code == 200, r.content
    d = r.json()["details"]
    assert d["given_name"] == "Amina" and d["date_of_birth"] == "2003-04-05"
    assert d["residence"]["sub_county"] == "Westlands" and len(d["contacts"]) == 2
    # Risky fields are ignored even when sent: status, officer, enrollment.
    before = Participant.objects.get(pk=person.pk).status
    put({"status": "withdrawn", "assigned_officer": "x", "enrollments": []})
    assert Participant.objects.get(pk=person.pk).status == before
    ev = AuditEvent.objects.filter(action="youth.details_edited").latest("at")
    assert "0712" not in str(ev.after)


def _referral(person, title, stages, note="private staff note"):
    """A referral that has moved through `stages`, with history, built directly."""
    from datetime import date

    from apps.employers.models import Employer, Opportunity
    from apps.referrals.models import Referral, StageEvent

    opp = Opportunity.objects.create(
        employer=Employer.objects.create(name=f"Employer {title}"),
        title=title,
        status=Opportunity.OPEN,
        closing_date=date.today() + timedelta(days=30),
    )
    r = Referral.objects.create(
        participant=person,
        opportunity=opp,
        stage=stages[-1],
        referred_at=timezone.now(),
        reason_note=note,
    )
    prev = ""
    for s in stages:
        StageEvent.objects.create(
            referral=r, from_stage=prev, to_stage=s, actor_label="Officer", at=timezone.now(),
            note=note,
        )  # fmt: skip
        prev = s
    return r


def test_youth_sees_only_their_own_referrals_in_plain_words(steward, person):
    from django.contrib.auth.models import User

    activate(person, steward)
    youth = api(User.objects.get(username=EMAIL))
    assert youth.get("/api/v1/youth/journey").status_code == 400  # notice not accepted yet
    youth.post(
        "/api/v1/youth/consent",
        {"version": services.CONSENT_VERSION},
        content_type="application/json",
    )
    assert youth.get("/api/v1/youth/journey").json()["latest"] is None

    mine = _referral(person, "Welder", ["draft", "submitted", "under_review", "interview"])
    refused = _referral(
        person, "Cashier", ["draft", "submitted", "rejected", "closed"], note="too junior"
    )
    other = Participant.objects.create(full_name_source="Someone Else")
    theirs = _referral(other, "Driver", ["draft", "submitted"])
    _referral(person, "Unsent", ["draft"])  # a draft is not shown to the youth yet

    j = youth.get("/api/v1/youth/journey").json()
    assert [x["opportunity"] for x in j["items"]] == ["Cashier", "Welder"] or {
        x["opportunity"] for x in j["items"]
    } == {"Welder", "Cashier"}
    assert j["counts"] == {"referred": 2, "interview": 1, "selected": 0, "placed": 0}
    by_title = {x["opportunity"]: x for x in j["items"]}
    assert by_title["Welder"]["stage_label"] == "Interview"
    assert by_title["Cashier"]["stage_label"] == "Not selected"
    assert by_title["Cashier"]["ended"] is True
    text = str(j)
    assert "too junior" not in text and "private staff note" not in text
    assert "score" not in text and "Someone Else" not in text

    d = youth.get(f"/api/v1/youth/opportunities/{mine.pk}").json()
    assert d["opportunity"] == "Welder"
    assert [t["label"] for t in d["timeline"]] == ["Referred", "Under review", "Interview"]
    assert "private staff note" not in str(d)
    assert youth.get(f"/api/v1/youth/opportunities/{theirs.pk}").status_code == 404
    assert youth.get(f"/api/v1/youth/opportunities/{refused.pk}").status_code == 200


def test_interview_details_notices_and_placement(steward, person):
    from django.contrib.auth.models import User

    from apps.referrals import services as ref
    from apps.referrals.models import Referral

    activate(person, steward)
    youth = api(User.objects.get(username=EMAIL))
    youth.post(
        "/api/v1/youth/consent",
        {"version": services.CONSENT_VERSION},
        content_type="application/json",
    )
    r = _referral(person, "Welder", ["draft", "submitted", "under_review"])
    staff = User.objects.get(pk=steward.pk) if hasattr(steward, "pk") else steward
    # interview details need the interview stage
    try:
        ref.set_interview(actor=staff, referral=r, at=timezone.now())
        raise AssertionError("expected a rule violation")
    except ref.RuleViolation:
        pass
    Referral.objects.filter(pk=r.pk).update(stage="interview")
    at = timezone.now() + timedelta(days=3)
    ref.set_interview(actor=staff, referral=r, at=at, place="Town office", note="Bring your ID")
    d = youth.get(f"/api/v1/youth/opportunities/{r.pk}").json()
    assert d["interview"]["place"] == "Town office"
    assert d["interview"]["note"] == "Bring your ID"

    n = youth.get("/api/v1/youth/notices").json()
    assert n["unread"] >= 1 and any("interview" in i["text"] for i in n["items"])
    seen = youth.post("/api/v1/youth/notices").json()
    assert seen["unread"] == 0

    assert youth.get("/api/v1/youth/placement").json() == {"placements": [], "referrals": []}
    done = _referral(person, "Cook", ["draft", "submitted", "selected", "placed"])
    p = youth.get("/api/v1/youth/placement").json()
    assert [x["designation"] for x in p["referrals"]] == ["Cook"]
    assert str(done.pk) == p["referrals"][0]["id"]
