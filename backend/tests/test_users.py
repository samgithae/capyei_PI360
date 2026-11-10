"""Staff account administration (T-036; FR-03, USR-02, SEC-08)."""

import pytest
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import Client
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.audit.models import AuditEvent
from apps.identity import services, users
from apps.identity.models import Role

JSON = "application/json"
BASE = "/api/v1/identity/users"


def actions():
    return list(AuditEvent.objects.order_by("pk").values_list("action", flat=True))


def signed_in(make_user, name="a", role="Administrator"):
    c = Client()
    c.force_login(make_user(name, role))
    return c


def post(c, url, data=None):
    return c.post(url, data or {}, content_type=JSON)


def test_create_user_without_password_and_audited(make_user):
    c = signed_in(make_user)
    r = post(c, BASE, {"username": "grace", "email": "Grace@Example.org", "roles": []})
    assert r.status_code == 201
    u = User.objects.get(username="grace")
    assert u.email == "grace@example.org" and not u.has_usable_password()
    assert "user.created" in actions()


def test_create_user_with_roles_and_duplicates(make_user):
    c = signed_in(make_user)
    rid = Role.objects.get(name="Placement officer").pk
    r = post(c, BASE, {"username": "o1", "email": "o1@example.org", "roles": [rid]})
    assert [x["name"] for x in r.json()["roles"]] == ["Placement officer"]
    dup = post(c, BASE, {"username": "O1", "email": "other@example.org"})
    assert dup.status_code == 400
    dup = post(c, BASE, {"username": "o2", "email": "O1@example.org"})
    assert dup.status_code == 400


def test_user_manager_without_role_rights_cannot_assign_roles(make_user):
    services.create_role(
        actor=None, name="User clerk", permissions=["identity.manage_users", "identity.view_users"]
    )
    c = Client()
    clerk = make_user("clerk")
    services.assign_role(actor=None, user=clerk, role=Role.objects.get(name="User clerk"))
    c.force_login(clerk)
    rid = Role.objects.get(name="Administrator").pk
    assert post(c, BASE, {"username": "x", "email": "x@e.org", "roles": [rid]}).status_code == 400
    assert post(c, BASE, {"username": "x", "email": "x@e.org"}).status_code == 201
    uid = User.objects.get(username="x").pk
    assert c.put(f"{BASE}/{uid}/roles", {"roles": [rid]}, content_type=JSON).status_code == 403


def test_list_search_and_filter(make_user):
    c = signed_in(make_user)
    make_user("alice")
    make_user("bob")
    User.objects.filter(username="bob").update(is_active=False)
    assert {u["username"] for u in c.get(BASE + "?q=ali").json()} == {"alice"}
    assert {u["username"] for u in c.get(BASE + "?active=false").json()} == {"bob"}


def test_edit_profile_audited_and_noop_is_silent(make_user):
    c = signed_in(make_user)
    u = make_user("t")
    r = c.patch(f"{BASE}/{u.pk}", {"first_name": "Tia"}, content_type=JSON)
    assert r.json()["first_name"] == "Tia"
    c.patch(f"{BASE}/{u.pk}", {"first_name": "Tia"}, content_type=JSON)
    assert actions().count("user.changed") == 1


def test_suspension_is_effective_on_the_next_request(make_user):
    admin = signed_in(make_user)
    victim = make_user("v", "Placement officer")
    vc = Client()
    vc.force_login(victim)
    assert vc.get("/api/v1/me").json()["authenticated"] is True
    r = post(admin, f"{BASE}/{victim.pk}/suspend", {"reason": "Left the organisation"})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert vc.get("/api/v1/me").json()["authenticated"] is False
    ev = AuditEvent.objects.get(action="user.suspended")
    assert ev.reason == "Left the organisation"


def test_suspension_ends_stored_sessions(make_user):
    victim = make_user("v")
    Client().force_login(victim)
    Client().force_login(victim)
    before = Session.objects.count()
    assert users.revoke_sessions(victim) == 2
    assert Session.objects.count() == before - 2


def test_suspend_rules(make_user):
    admin_user = make_user("a", "Administrator")
    c = Client()
    c.force_login(admin_user)
    assert post(c, f"{BASE}/{admin_user.pk}/suspend", {"reason": "x"}).status_code == 400  # self
    other = make_user("v")
    assert post(c, f"{BASE}/{other.pk}/suspend", {"reason": " "}).status_code == 400  # no reason
    second = make_user("b", "Administrator")
    c2 = Client()
    c2.force_login(second)
    assert post(c2, f"{BASE}/{admin_user.pk}/suspend", {"reason": "x"}).status_code == 200
    assert post(c2, f"{BASE}/{second.pk}/suspend", {"reason": "x"}).status_code == 400


def test_last_administrator_cannot_be_suspended_by_a_system_actor(make_user):
    only = make_user("a", "Administrator")
    with pytest.raises(services.AccessError):
        users.suspend_user(actor=None, user=only, reason="x")


def test_reactivate(make_user):
    c = signed_in(make_user)
    v = make_user("v")
    post(c, f"{BASE}/{v.pk}/suspend", {"reason": "leave"})
    r = post(c, f"{BASE}/{v.pk}/reactivate")
    assert r.json()["is_active"] is True
    assert actions()[-2:] == ["user.suspended", "user.reactivated"]


def test_reset_mfa_removes_device_and_sessions(make_user):
    c = signed_in(make_user)
    v = make_user("v", "Manager")
    TOTPDevice.objects.create(user=v, name="authenticator", confirmed=True)
    Client().force_login(v)
    assert post(c, f"{BASE}/{v.pk}/reset-mfa", {"reason": "Lost phone"}).status_code == 200
    assert not TOTPDevice.objects.filter(user=v).exists()
    assert post(c, f"{BASE}/{v.pk}/reset-mfa", {}).status_code == 400  # reason needed
    assert "user.mfa_reset" in actions()


def test_set_roles_and_scopes_through_the_api(make_user):
    c = signed_in(make_user)
    v = make_user("v")
    ids = {r.name: r.pk for r in Role.objects.all()}
    r = c.put(
        f"{BASE}/{v.pk}/roles",
        {"roles": [ids["Placement officer"], ids["M&E analyst"]]},
        content_type=JSON,
    )
    assert {x["name"] for x in r.json()["roles"]} == {"Placement officer", "M&E analyst"}
    r = c.put(f"{BASE}/{v.pk}/roles", {"roles": [ids["Manager"]]}, content_type=JSON)
    assert [x["name"] for x in r.json()["roles"]] == ["Manager"]
    r = c.put(f"{BASE}/{v.pk}/roles", {"roles": [99999]}, content_type=JSON)
    assert r.status_code == 400
    r = c.put(
        f"{BASE}/{v.pk}/scopes",
        {"scopes": [{"kind": "region", "value": "Kilifi"}]},
        content_type=JSON,
    )
    assert r.json()["scopes"] == [{"kind": "region", "value": "Kilifi"}]
    bad = c.put(
        f"{BASE}/{v.pk}/scopes", {"scopes": [{"kind": "x", "value": "1"}]}, content_type=JSON
    )
    assert bad.status_code == 400


def test_cannot_strip_the_last_administrator_role(make_user):
    c = signed_in(make_user)
    me = User.objects.get(username="a")
    r = c.put(f"{BASE}/{me.pk}/roles", {"roles": []}, content_type=JSON)
    assert r.status_code == 400


def test_unknown_user_is_404(make_user):
    c = signed_in(make_user)
    assert c.get(f"{BASE}/999999").status_code == 404
