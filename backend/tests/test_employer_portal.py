"""Employer portal foundations: staff set up the first account, a company admin runs the team,
one company never sees another, and the two switches (MFA, self-publish) default to off."""

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import Client

from apps.configuration import services as configuration
from apps.employer_portal import services
from apps.employer_portal.models import EmployerInvite, EmployerMember
from apps.employers.models import Employer
from apps.identity import services as identity
from apps.identity.defaults import DEFAULT_ROLES
from apps.identity.models import Role

PASSWORD = "a-much-longer-passphrase-9"  # noqa: S105 (test value)
JSON = "application/json"


def api(user=None):
    c = Client()
    if user:
        c.force_login(user)
    return c


@pytest.fixture(autouse=True)
def _fresh_throttle():
    cache.clear()


@pytest.fixture
def steward(make_user):
    return make_user("steward", "Data steward")


@pytest.fixture
def acme(db):
    return Employer.objects.create(name="Acme Traders")


@pytest.fixture
def beta(db):
    return Employer.objects.create(name="Beta Logistics")


def role_id(name):
    return Role.objects.get(name=name).pk


def token_from_mail():
    return mail.outbox[-1].body.split("#token=")[1].split()[0]


def staff_invite(steward, employer, email="dir@acme.example", role="Company admin", **extra):
    return api(steward).post(
        f"/api/v1/employers/{employer.pk}/users",
        {"email": email, "full_name": "Wanjiru Director", "role_id": role_id(role), **extra},
        content_type=JSON,
    )


def activate(token=None, password=PASSWORD):
    return api().post(
        "/api/v1/employer/activate",
        {"token": token or token_from_mail(), "password": password},
        content_type=JSON,
    )


def onboard(steward, employer, email="dir@acme.example", role="Company admin"):
    """Invite, activate and return the signed-in user."""
    assert staff_invite(steward, employer, email, role).status_code == 201
    assert activate().status_code == 204
    return User.objects.get(username=email)


@pytest.fixture
def admin(steward, acme):
    return onboard(steward, acme)


def company_invite(user, email="hr@acme.example", role="HR / Recruiter"):
    return api(user).post(
        "/api/v1/employer/staff",
        {"email": email, "full_name": "Otieno HR", "role_id": role_id(role)},
        content_type=JSON,
    )


# ---- roles -------------------------------------------------------------------------------------


def test_the_four_employer_roles_exist_and_are_employer_only(db):
    identity.ensure_default_roles()
    names = {r["name"] for r in services.assignable_roles()}
    assert names == {"Company admin", "HR / Recruiter", "Hiring manager", "Employer viewer"}
    for r in DEFAULT_ROLES:
        if r["name"] in names:
            assert all(c.startswith("employer.") for c in r["permissions"])


def test_a_company_role_never_holds_a_staff_permission(db):
    identity.ensure_default_roles()
    for r in services.assignable_roles():
        assert not any(c.startswith(("participants.", "employers.")) for c in r["permissions"])


# ---- staff set up the first account -------------------------------------------------------------


def test_staff_invite_then_the_person_activates_and_signs_in(steward, acme):
    r = staff_invite(steward, acme)
    assert r.status_code == 201
    row = r.json()
    assert row["state"] == "pending" and row["is_owner"] is True
    assert "#token=" in mail.outbox[-1].body and "/employer/activate" in mail.outbox[-1].body
    assert activate().status_code == 204
    login = api().post(
        "/api/v1/auth/login",
        {"username": "dir@acme.example", "password": PASSWORD},
        content_type=JSON,
    )
    assert login.json()["status"] == "ok"


def test_only_the_first_account_is_the_owner(steward, acme, admin):
    r = staff_invite(steward, acme, email="second@acme.example")
    assert r.json()["is_owner"] is False


def test_the_invite_link_works_once(steward, acme):
    staff_invite(steward, acme)
    token = token_from_mail()
    assert activate(token).status_code == 204
    assert activate(token, "another-long-passphrase-7").status_code == 400


def test_an_expired_invite_is_refused(steward, acme):
    from datetime import timedelta

    from django.utils import timezone

    staff_invite(steward, acme)
    token = token_from_mail()
    EmployerInvite.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    r = api().post("/api/v1/employer/activate/check", {"token": token}, content_type=JSON)
    assert r.status_code == 400
    assert activate(token).status_code == 400


def test_a_guessed_token_is_refused(db):
    r = api().post("/api/v1/employer/activate/check", {"token": "nope"}, content_type=JSON)
    assert r.status_code == 400


def test_the_token_and_address_never_reach_the_audit_log(steward, acme):
    from apps.audit.models import AuditEvent

    staff_invite(steward, acme)
    token = token_from_mail()
    blob = " ".join(str(e.after) + str(e.before) for e in AuditEvent.objects.all())
    assert token not in blob and "dir@acme.example" not in blob
    assert AuditEvent.objects.filter(action="employer_user.invited").exists()


def test_inviting_the_same_pending_address_replaces_the_invite(steward, acme):
    staff_invite(steward, acme)
    first = token_from_mail()
    assert staff_invite(steward, acme).status_code == 201
    assert EmployerMember.objects.count() == 1
    assert activate(first).status_code == 400
    assert activate().status_code == 204


def test_an_address_that_already_has_an_account_is_refused(steward, acme, admin):
    assert staff_invite(steward, acme).status_code == 400


def test_a_staff_role_cannot_be_handed_to_an_employer_user(steward, acme):
    r = staff_invite(steward, acme, role="Administrator")
    assert r.status_code == 400
    assert not EmployerMember.objects.exists()


def test_an_inactive_employer_cannot_be_invited_to(steward, acme):
    Employer.objects.filter(pk=acme.pk).update(status=Employer.INACTIVE)
    assert staff_invite(steward, acme).status_code == 400


def test_staff_without_the_permission_cannot_invite(make_user, acme):
    officer = make_user("officer", "Placement officer")
    assert staff_invite(officer, acme).status_code == 403


def test_staff_see_an_employers_users_and_the_roles_on_offer(steward, acme, admin):
    data = api(steward).get(f"/api/v1/employers/{acme.pk}/users").json()
    assert [u["state"] for u in data["users"]] == ["active"]
    assert {r["name"] for r in data["roles"]} >= {"Company admin", "Employer viewer"}


# ---- the company side ---------------------------------------------------------------------------


def test_me_names_the_company_and_the_role(admin, acme):
    me = api(admin).get("/api/v1/employer/me").json()
    assert me["employer"]["name"] == "Acme Traders"
    assert me["roles"] == ["Company admin"] and me["member"]["is_owner"] is True


def test_a_staff_user_has_no_employer_portal(steward):
    assert api(steward).get("/api/v1/employer/me").status_code == 403


def test_a_company_admin_invites_a_colleague_who_gets_only_that_role(admin):
    assert company_invite(admin).status_code == 201
    token = token_from_mail()
    assert activate(token).status_code == 204
    hr = User.objects.get(username="hr@acme.example")
    me = api(hr).get("/api/v1/employer/me").json()
    assert me["roles"] == ["HR / Recruiter"] and me["member"]["is_owner"] is False
    # HR can work with referrals but cannot manage the team
    assert api(hr).get("/api/v1/employer/staff").status_code == 403


def test_a_company_admin_cannot_hand_out_a_staff_role(admin):
    r = api(admin).post(
        "/api/v1/employer/staff",
        {"email": "x@acme.example", "full_name": "X", "role_id": role_id("Administrator")},
        content_type=JSON,
    )
    assert r.status_code == 400


def test_the_team_list_is_only_the_own_company(steward, acme, beta, admin):
    onboard(steward, beta, email="dir@beta.example")
    rows = api(admin).get("/api/v1/employer/staff").json()
    assert [r["email"] for r in rows] == ["dir@acme.example"]


def test_one_company_cannot_touch_another_companys_people(steward, acme, beta, admin):
    other = onboard(steward, beta, email="dir@beta.example")
    theirs = EmployerMember.objects.get(user=other)
    url = f"/api/v1/employer/staff/{theirs.pk}"
    changed = api(admin).patch(url, {"role_id": role_id("Employer viewer")}, content_type=JSON)
    assert changed.status_code == 404
    off = api(admin).patch(url, {"active": False, "reason": "x"}, content_type=JSON)
    assert off.status_code == 404
    assert api(admin).delete(url).status_code == 404
    assert identity.role_names(other) == ["Company admin"]


def test_a_company_admin_changes_a_colleagues_role(admin):
    company_invite(admin)
    activate()
    hr = User.objects.get(username="hr@acme.example")
    member = EmployerMember.objects.get(user=hr)
    r = api(admin).patch(
        f"/api/v1/employer/staff/{member.pk}",
        {"role_id": role_id("Hiring manager")},
        content_type=JSON,
    )
    assert r.status_code == 200 and r.json()["roles"] == ["Hiring manager"]


def test_the_last_company_admin_cannot_be_demoted_or_suspended(admin):
    member = EmployerMember.objects.get(user=admin)
    url = f"/api/v1/employer/staff/{member.pk}"
    demote = api(admin).patch(url, {"role_id": role_id("Employer viewer")}, content_type=JSON)
    assert demote.status_code == 400
    off = api(admin).patch(url, {"active": False, "reason": "left"}, content_type=JSON)
    assert off.status_code == 400
    assert identity.role_names(admin) == ["Company admin"]


def test_suspend_signs_the_person_out_and_reactivate_restores_them(admin):
    company_invite(admin)
    activate()
    hr = User.objects.get(username="hr@acme.example")
    member = EmployerMember.objects.get(user=hr)
    url = f"/api/v1/employer/staff/{member.pk}"
    off = api(admin).patch(url, {"active": False, "reason": "left the company"}, content_type=JSON)
    assert off.status_code == 200 and off.json()["state"] == "suspended"
    assert (
        api()
        .post(
            "/api/v1/auth/login",
            {"username": "hr@acme.example", "password": PASSWORD},
            content_type=JSON,
        )
        .json()["status"]
        != "ok"
    )
    on = api(admin).patch(url, {"active": True}, content_type=JSON)
    assert on.json()["state"] == "active"


def test_suspending_needs_a_reason(admin):
    company_invite(admin)
    activate()
    member = EmployerMember.objects.get(user__username="hr@acme.example")
    r = api(admin).patch(
        f"/api/v1/employer/staff/{member.pk}", {"active": False}, content_type=JSON
    )
    assert r.status_code == 400


def test_an_unaccepted_invite_can_be_withdrawn(admin):
    company_invite(admin)
    token = token_from_mail()
    member = EmployerMember.objects.get(user__username="hr@acme.example")
    assert api(admin).delete(f"/api/v1/employer/staff/{member.pk}").status_code == 204
    assert not User.objects.filter(username="hr@acme.example").exists()
    assert activate(token).status_code == 400


def test_an_accepted_account_cannot_be_withdrawn(admin):
    company_invite(admin)
    activate()
    member = EmployerMember.objects.get(user__username="hr@acme.example")
    assert api(admin).delete(f"/api/v1/employer/staff/{member.pk}").status_code == 400


def test_an_inactive_company_locks_its_people_out(admin, acme):
    Employer.objects.filter(pk=acme.pk).update(status=Employer.INACTIVE)
    assert api(admin).get("/api/v1/employer/me").status_code == 404


def test_an_archived_company_locks_its_people_out(admin, acme):
    from django.utils import timezone

    Employer.objects.filter(pk=acme.pk).update(archived_at=timezone.now())
    assert api(admin).get("/api/v1/employer/me").status_code == 404
    assert services.mfa_required(admin) is False  # the switch is off by default


# ---- the two switches ---------------------------------------------------------------------------


def test_the_switches_exist_and_are_off_by_default(db):
    assert configuration.is_enabled("employer_mfa_required") is False
    assert configuration.is_enabled("employer_self_publish") is False


def test_mfa_is_off_for_employers_by_default(admin):
    assert services.mfa_required(admin) is False


def test_mfa_applies_to_employer_users_once_the_switch_is_on(admin):
    configuration.set_flag(actor=None, key="employer_mfa_required", enabled=True)
    assert services.mfa_required(admin) is True


def test_the_mfa_switch_can_name_company_admins_only(steward, admin):
    configuration.set_flag(
        actor=None, key="employer_mfa_required", enabled=True, roles=["Company admin"]
    )
    company_invite(admin)
    activate()
    hr = User.objects.get(username="hr@acme.example")
    assert services.mfa_required(admin) is True
    assert services.mfa_required(hr) is False


def test_the_employer_mfa_switch_does_not_touch_staff_or_youth(steward):
    configuration.set_flag(actor=None, key="employer_mfa_required", enabled=True)
    assert services.mfa_required(steward) is False


def test_with_the_switch_on_an_employer_must_set_up_a_second_factor_to_sign_in(admin):
    configuration.set_flag(actor=None, key="employer_mfa_required", enabled=True)
    r = api().post(
        "/api/v1/auth/login",
        {"username": "dir@acme.example", "password": PASSWORD},
        content_type=JSON,
    )
    assert r.json()["status"] != "ok"
