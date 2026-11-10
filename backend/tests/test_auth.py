"""Staff authentication (T-034; FR-01, SEC-08, SEC-10, SEC-11)."""

import time

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.test import Client
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.audit.models import AuditEvent
from apps.identity.models import LoginLockout

PW = "correct horse battery 42"
NEW_PW = "another long passphrase 77"
L = "/api/v1/auth/login"


@pytest.fixture(autouse=True)
def _clear_throttle():
    from django.core.cache import cache

    cache.clear()


def code_for(device):
    t = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    t.time = time.time()
    return f"{t.token():06d}"


def post(c, url, **data):
    return c.post(url, data, content_type="application/json")


@pytest.fixture
def staff(db):
    return User.objects.create_user("amina", "amina@example.org", PW)


@pytest.fixture
def admin(make_user):
    u = make_user("admin1", "Administrator")
    u.set_password(PW)
    u.save()
    return u


def actions():
    return list(AuditEvent.objects.order_by("pk").values_list("action", flat=True))


# --- sign-in -------------------------------------------------------------


def test_login_ok_then_me(staff):
    c = Client()
    r = post(c, L, username="amina", password=PW)
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert c.get("/api/v1/me").json()["username"] == "amina"
    assert "auth.login" in actions()


def test_wrong_password_is_401_and_audited(staff):
    r = post(Client(), L, username="amina", password="nope")
    assert r.status_code == 401
    assert r.json()["type"].endswith("invalid-credentials")
    assert actions() == ["auth.login_failed"]


def test_unknown_user_same_answer_no_username_stored(db):
    r = post(Client(), L, username="ghost", password="whatever")
    assert r.status_code == 401 and r.json()["detail"] == "Incorrect username or password."
    ev = AuditEvent.objects.get()
    assert ev.object_id == "unknown" and "ghost" not in str(ev.__dict__)


def test_unauthenticated_requests_rejected_with_401(db):
    assert Client().get("/api/v1/audit/events").status_code == 401


def test_login_requires_csrf_token(staff):
    c = Client(enforce_csrf_checks=True)
    r = post(c, L, username="amina", password=PW)
    assert r.status_code == 403 and r.json()["type"].endswith("csrf-failed")
    c.get("/api/v1/me")  # sets the cookie
    token = c.cookies["csrftoken"].value
    r = c.post(
        L,
        {"username": "amina", "password": PW},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert r.status_code == 200


# --- lockout -------------------------------------------------------------


def test_lockout_after_configured_failures(staff, settings):
    settings.AUTH_MAX_FAILURES = 3
    c = Client()
    for _ in range(3):
        assert post(c, L, username="amina", password="bad").status_code == 401
    r = post(c, L, username="amina", password=PW)  # right password, but locked
    assert r.status_code == 429 and "Retry-After" in r
    assert "auth.lockout" in actions()


def test_lockout_also_applies_to_unknown_usernames(db, settings):
    settings.AUTH_MAX_FAILURES = 2
    for _ in range(2):
        post(Client(), L, username="ghost", password="x")
    assert post(Client(), L, username="ghost", password="x").status_code == 429


def test_success_clears_failures(staff, settings):
    settings.AUTH_MAX_FAILURES = 3
    post(Client(), L, username="amina", password="bad")
    post(Client(), L, username="amina", password="bad")
    assert post(Client(), L, username="amina", password=PW).status_code == 200
    assert not LoginLockout.objects.exists()


def test_lockout_expires(staff, settings):
    settings.AUTH_MAX_FAILURES = 1
    settings.AUTH_LOCKOUT_SECONDS = 60
    post(Client(), L, username="amina", password="bad")
    LoginLockout.objects.update(
        locked_until=LoginLockout.objects.get().locked_until.replace(year=2020)
    )
    assert post(Client(), L, username="amina", password=PW).status_code == 200


# --- sessions and suspension ---------------------------------------------


def test_logout_ends_session(staff):
    c = Client()
    post(c, L, username="amina", password=PW)
    assert post(c, "/api/v1/auth/logout").status_code == 204
    assert c.get("/api/v1/me").json() == {"authenticated": False}
    assert "auth.logout" in actions()


def test_absolute_timeout_ends_session(staff, settings):
    settings.SESSION_ABSOLUTE_SECONDS = 60
    c = Client()
    post(c, L, username="amina", password=PW)
    s = c.session
    s["auth_started_at"] = time.time() - 120
    s.save()
    assert c.get("/api/v1/me").json() == {"authenticated": False}


def test_idle_timeout_is_configured(settings):
    assert settings.SESSION_SAVE_EVERY_REQUEST is True
    assert settings.SESSION_COOKIE_AGE == 30 * 60
    assert settings.SESSION_COOKIE_HTTPONLY is True


def test_suspended_user_loses_access_on_next_request(staff):
    c = Client()
    post(c, L, username="amina", password=PW)
    assert c.get("/api/v1/me").json()["authenticated"] is True
    User.objects.filter(pk=staff.pk).update(is_active=False)
    assert c.get("/api/v1/me").json() == {"authenticated": False}


def test_suspended_user_cannot_sign_in(staff):
    User.objects.filter(pk=staff.pk).update(is_active=False)
    assert post(Client(), L, username="amina", password=PW).status_code == 401


# --- MFA -----------------------------------------------------------------


def test_admin_password_alone_does_not_sign_in(admin):
    c = Client()
    r = post(c, L, username="admin1", password=PW)
    assert r.json() == {"status": "mfa_required", "mfa_enrolled": False}
    assert c.get("/api/v1/me").json() == {"authenticated": False}
    assert "auth.login" not in actions()


def test_admin_enrols_then_signs_in_with_code(admin):
    c = Client()
    post(c, L, username="admin1", password=PW)
    url = post(c, "/api/v1/auth/mfa/setup").json()["config_url"]
    assert url.startswith("otpauth://totp/")
    device = TOTPDevice.objects.get(user=admin)
    assert post(c, "/api/v1/auth/mfa/confirm", code="000000").status_code == 401
    # django-otp delays the next attempt after a failure; skip the wait in the test
    TOTPDevice.objects.filter(pk=device.pk).update(throttling_failure_count=0)
    device.refresh_from_db()
    assert post(c, "/api/v1/auth/mfa/confirm", code=code_for(device)).status_code == 200
    assert c.get("/api/v1/me").json()["username"] == "admin1"
    assert "auth.mfa_enrolled" in actions()

    # next sign-in: enrolled, so verify (replay of the same code is refused)
    c2 = Client()
    r = post(c2, L, username="admin1", password=PW)
    assert r.json() == {"status": "mfa_required", "mfa_enrolled": True}
    assert post(c2, "/api/v1/auth/mfa/verify", code=code_for(device)).status_code == 401
    TOTPDevice.objects.filter(pk=device.pk).update(last_t=-1, throttling_failure_count=0)
    device.refresh_from_db()
    assert post(c2, "/api/v1/auth/mfa/verify", code=code_for(device)).status_code == 200


def test_mfa_setup_blocked_once_enrolled(admin):
    TOTPDevice.objects.create(user=admin, name="authenticator", confirmed=True)
    c = Client()
    post(c, L, username="admin1", password=PW)
    assert post(c, "/api/v1/auth/mfa/setup").status_code == 403


def test_mfa_endpoints_need_a_password_step_first(admin):
    assert post(Client(), "/api/v1/auth/mfa/verify", code="123456").status_code == 409


def test_mfa_pending_expires(admin, settings):
    settings.AUTH_MFA_PENDING_SECONDS = 60
    c = Client()
    post(c, L, username="admin1", password=PW)
    s = c.session
    s["mfa_pending_at"] = time.time() - 120
    s.save()
    assert post(c, "/api/v1/auth/mfa/setup").status_code == 409


def test_mfa_gives_up_after_repeated_wrong_codes(admin):
    TOTPDevice.objects.create(user=admin, name="authenticator", confirmed=True)
    c = Client()
    post(c, L, username="admin1", password=PW)
    for _ in range(5):
        assert post(c, "/api/v1/auth/mfa/verify", code="000000").status_code == 401
    assert post(c, "/api/v1/auth/mfa/verify", code="000000").status_code == 409
    assert actions().count("auth.mfa_failed") == 5


def test_mfa_required_for_django_staff_and_all_staff_flag(staff, settings):
    assert post(Client(), L, username="amina", password=PW).json()["status"] == "ok"
    settings.AUTH_MFA_ALL_STAFF = True
    assert post(Client(), L, username="amina", password=PW).json()["status"] == "mfa_required"


# --- passwords -----------------------------------------------------------


def test_password_change(staff):
    c = Client()
    post(c, L, username="amina", password=PW)
    u = "/api/v1/auth/password/change"
    assert post(c, u, current_password="bad", new_password=NEW_PW).status_code == 400
    assert post(c, u, current_password=PW, new_password="short").status_code == 400
    assert post(c, u, current_password=PW, new_password=NEW_PW).status_code == 204
    assert c.get("/api/v1/me").json()["authenticated"] is True  # this session survives
    assert post(Client(), L, username="amina", password=NEW_PW).status_code == 200
    assert "auth.password_changed" in actions()


def test_password_change_needs_sign_in(db):
    r = post(Client(), "/api/v1/auth/password/change", current_password="a", new_password="b")
    assert r.status_code == 401


def _reset_link(body):
    q = body.split("reset-password?")[1].split()[0]
    return dict(p.split("=") for p in q.split("&"))


def test_password_reset_flow_is_audited_and_single_use(staff):
    r = post(Client(), "/api/v1/auth/password/reset", email="amina@example.org")
    assert r.status_code == 202 and len(mail.outbox) == 1
    args = _reset_link(mail.outbox[0].body)
    c = Client()
    done = post(c, "/api/v1/auth/password/reset/confirm", new_password=NEW_PW, **args)
    assert done.status_code == 204
    assert post(Client(), L, username="amina", password=NEW_PW).status_code == 200
    again = post(Client(), "/api/v1/auth/password/reset/confirm", new_password=PW + "x", **args)
    assert again.status_code == 400
    assert {"auth.password_reset_requested", "auth.password_reset"} <= set(actions())


def test_password_reset_does_not_reveal_unknown_email(db):
    r = post(Client(), "/api/v1/auth/password/reset", email="nobody@example.org")
    assert r.status_code == 202 and mail.outbox == []


def test_password_reset_rejects_bad_token_and_weak_password(staff):
    uid = urlsafe_base64_encode(force_bytes(staff.pk))
    u = "/api/v1/auth/password/reset/confirm"
    assert post(Client(), u, uid=uid, token="bad", new_password=NEW_PW).status_code == 400
    post(Client(), "/api/v1/auth/password/reset", email="amina@example.org")
    args = _reset_link(mail.outbox[0].body)
    assert post(Client(), u, new_password="short", **args).status_code == 400


def test_reset_clears_lockout_and_old_sessions(staff, settings):
    settings.AUTH_MAX_FAILURES = 1
    old = Client()
    post(old, L, username="amina", password=PW)
    post(Client(), L, username="amina", password="bad")  # locks the account
    post(Client(), "/api/v1/auth/password/reset", email="amina@example.org")
    args = _reset_link(mail.outbox[0].body)
    post(Client(), "/api/v1/auth/password/reset/confirm", new_password=NEW_PW, **args)
    assert old.get("/api/v1/me").json() == {"authenticated": False}
    assert post(Client(), L, username="amina", password=NEW_PW).status_code == 200


def test_admin_site_is_off_unless_enabled(client, settings):
    from django.urls import resolve
    from django.urls.exceptions import Resolver404

    if not settings.ENABLE_ADMIN:
        with pytest.raises(Resolver404):
            resolve("/admin/")
