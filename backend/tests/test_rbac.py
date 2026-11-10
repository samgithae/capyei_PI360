"""Roles, permissions and record scope (T-035; FR-04, SEC-05..07, SEC-18, USR-09)."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from apps.api import access
from apps.api.access import ScopedQuerySet
from apps.audit.models import AuditEvent
from apps.identity import services
from apps.identity.catalogue import GRANT_ONLY, ROLE_ASSIGNABLE
from apps.identity.defaults import DEFAULT_ROLES
from apps.identity.models import Role

JSON = "application/json"


def actions():
    return list(AuditEvent.objects.order_by("pk").values_list("action", flat=True))


def perms(user):
    user = User.objects.get(pk=user.pk)  # fresh instance: access is cached per request
    return access.permissions_of(user)


# --- catalogue and shipped roles -------------------------------------------


def test_default_roles_only_use_known_assignable_permissions():
    for spec in DEFAULT_ROLES:
        assert set(spec["permissions"]) <= ROLE_ASSIGNABLE, spec["name"]


def test_restricted_permissions_are_in_no_default_role():
    used = {p for spec in DEFAULT_ROLES for p in spec["permissions"]}
    assert not used & GRANT_ONLY
    assert {"restricted.view_background", "restricted.view_national_id"} <= GRANT_ONLY


def test_shipped_roles_exist_and_assessor_is_off(db):
    services.ensure_default_roles()
    names = set(Role.objects.values_list("name", flat=True))
    assert {"Administrator", "Data steward", "Placement officer", "Manager", "M&E analyst"} <= names
    assert Role.objects.get(name="Assessor").active is False


def test_ensure_default_roles_never_overwrites_edits(db):
    services.ensure_default_roles()
    role = Role.objects.get(name="Manager")
    services.update_role(actor=None, role=role, permissions=["referrals.view"])
    services.ensure_default_roles()
    assert Role.objects.get(name="Manager").permissions == ["referrals.view"]


# --- effective permissions --------------------------------------------------


def test_officer_gets_role_permissions_only(make_user):
    officer = make_user("o", "Placement officer")
    p = perms(officer)
    assert "participants.edit" in p and "audit.view" not in p
    assert not p & GRANT_ONLY


def test_user_without_role_has_nothing(make_user):
    assert perms(make_user("nobody")) == frozenset()


def test_permissions_union_across_roles(make_user):
    u = make_user("both", "Placement officer")
    services.assign_role(actor=None, user=u, role=Role.objects.get(name="M&E analyst"))
    p = perms(u)
    assert "participants.edit" in p and "exports.deidentified" in p


def test_inactive_role_confers_nothing(make_user):
    u = make_user("x", "Assessor")
    assert perms(u) == frozenset()
    services.update_role(actor=None, role=Role.objects.get(name="Assessor"), active=True)
    assert "ydm.assess" in perms(u)


def test_suspended_user_has_no_permissions(make_user):
    u = make_user("x", "Administrator")
    User.objects.filter(pk=u.pk).update(is_active=False)
    assert perms(u) == frozenset()


def test_superuser_still_needs_a_grant_for_restricted_data(db):
    root = User.objects.create_superuser("root", password="a-long-test-password")
    p = perms(root)
    assert "identity.manage_roles" in p
    assert not p & GRANT_ONLY


# --- grants (SEC-18) ---------------------------------------------------------


def test_grant_gives_restricted_permission_until_expiry_and_is_audited(make_user):
    steward = make_user("s", "Data steward")
    admin = make_user("a", "Administrator")
    assert "restricted.view_background" not in perms(steward)
    grant = services.grant_permission(
        actor=admin,
        user=steward,
        permission="restricted.view_background",
        purpose="Reconcile intake errors",
        expires_at=timezone.now() + timedelta(days=7),
    )
    assert "restricted.view_background" in perms(steward)
    grant.expires_at = timezone.now() - timedelta(seconds=1)
    grant.save()
    assert "restricted.view_background" not in perms(steward)
    assert "permission.granted" in actions()


def test_grant_can_be_revoked(make_user):
    steward = make_user("s", "Data steward")
    g = services.grant_permission(
        actor=None,
        user=steward,
        permission="restricted.view_national_id",
        purpose="Duplicate check",
        expires_at=timezone.now() + timedelta(days=1),
    )
    services.revoke_grant(actor=None, grant=g, reason="done")
    assert "restricted.view_national_id" not in perms(steward)
    assert "permission.revoked" in actions()


def test_grant_rules(make_user):
    u = make_user("s", "Data steward")
    future = timezone.now() + timedelta(days=1)
    with pytest.raises(services.AccessError):  # not a restricted permission
        services.grant_permission(
            actor=None, user=u, permission="audit.view", purpose="x", expires_at=future
        )
    with pytest.raises(services.AccessError):  # no purpose
        services.grant_permission(
            actor=None, user=u, permission="exports.identifiable", purpose=" ", expires_at=future
        )
    with pytest.raises(services.AccessError):  # already expired
        services.grant_permission(
            actor=None,
            user=u,
            permission="exports.identifiable",
            purpose="x",
            expires_at=timezone.now() - timedelta(days=1),
        )


def test_restricted_permission_cannot_be_put_in_a_role(db):
    with pytest.raises(services.AccessError):
        services.create_role(actor=None, name="Snoop", permissions=["restricted.view_background"])
    with pytest.raises(services.AccessError):
        services.create_role(actor=None, name="Bad", permissions=["no.such.permission"])


# --- role administration rules ---------------------------------------------


def test_role_lifecycle_is_audited(db):
    role = services.create_role(actor=None, name="Field agent", permissions=["participants.view"])
    services.update_role(
        actor=None, role=role, permissions=["participants.view", "placements.view"]
    )
    services.delete_role(actor=None, role=role)
    assert actions() == ["role.created", "role.changed", "role.deleted"]


def test_shipped_roles_cannot_be_deleted_or_renamed(db):
    services.ensure_default_roles()
    role = Role.objects.get(name="Manager")
    with pytest.raises(services.AccessError):
        services.delete_role(actor=None, role=role)
    with pytest.raises(services.AccessError):
        services.update_role(actor=None, role=role, name="Boss")


def test_role_in_use_cannot_be_deleted(make_user):
    role = services.create_role(actor=None, name="Temp", permissions=["participants.view"])
    services.assign_role(actor=None, user=make_user("u"), role=role)
    with pytest.raises(services.AccessError):
        services.delete_role(actor=None, role=role)


def test_administrator_cannot_lock_itself_out(db):
    services.ensure_default_roles()
    admin = Role.objects.get(name="Administrator")
    with pytest.raises(services.AccessError):
        services.update_role(actor=None, role=admin, permissions=["audit.view"])
    with pytest.raises(services.AccessError):
        services.update_role(actor=None, role=admin, active=False)


def test_role_change_takes_effect_on_next_request(make_user):
    role = services.create_role(actor=None, name="Reader", permissions=["participants.view"])
    u = make_user("u")
    services.assign_role(actor=None, user=u, role=role)
    assert "placements.view" not in perms(u)
    services.update_role(
        actor=None, role=role, permissions=["participants.view", "placements.view"]
    )
    assert "placements.view" in perms(u)


def test_role_and_scope_assignment_audited(make_user):
    u = make_user("u")
    services.set_scopes(actor=None, user=u, scopes=[("cohort", "7"), ("region", "Kilifi")])
    services.set_scopes(
        actor=None, user=u, scopes=[("cohort", "7"), ("region", "Kilifi")]
    )  # no change
    services.set_scopes(actor=None, user=u, scopes=[("cohort", "8")])
    assert actions().count("scope.assigned") == 2
    with pytest.raises(services.AccessError):
        services.set_scopes(actor=None, user=u, scopes=[("galaxy", "1")])


# --- record scope (SEC-07, USR-09) -----------------------------------------
# Scope mapping is exercised on the User table, which has real columns to filter.

MAP = {"cohort": "last_name", "region": "first_name", "officer": "pk"}


@pytest.fixture
def people(db):
    rows = [
        ("a", "Kilifi", "c1"),
        ("b", "Kilifi", "c2"),
        ("c", "Kwale", "c1"),
        ("d", "Kwale", "c2"),
    ]
    return {
        n: User.objects.create_user(n, first_name=r, last_name=c, password="x") for n, r, c in rows
    }


def visible(user, people):
    q = access.scope_q(User.objects.get(pk=user.pk), MAP)
    return sorted(
        User.objects.filter(q)
        .filter(pk__in=[p.pk for p in people.values()])
        .values_list("username", flat=True)
    )


def test_scoped_user_with_no_assignment_sees_nothing(make_user, people):
    assert visible(make_user("officer", "Placement officer"), people) == []


def test_scope_is_or_within_a_kind_and_across_kinds(make_user, people):
    o = make_user("officer", "Placement officer")
    services.set_scopes(actor=None, user=o, scopes=[("cohort", "c1"), ("cohort", "c2")])
    assert visible(o, people) == ["a", "b", "c", "d"]
    services.set_scopes(actor=None, user=o, scopes=[("cohort", "c1"), ("region", "Kilifi")])
    assert visible(o, people) == ["a"]


def test_scope_kind_the_model_cannot_use_denies(make_user, people):
    o = make_user("officer", "Placement officer")
    services.set_scopes(actor=None, user=o, scopes=[("programme", "p1")])
    assert visible(o, people) == []


def test_officer_self_scope(make_user, people):
    o = make_user("officer", "Placement officer")
    services.set_scopes(actor=None, user=o, scopes=[("officer", "self")])
    assert visible(o, people) == []  # o is not one of the listed people
    people["o"] = o
    assert visible(o, people) == ["officer"]


def test_organisation_wide_role_sees_everything(make_user, people):
    assert visible(make_user("steward", "Data steward"), people) == ["a", "b", "c", "d"]


def test_anonymous_sees_nothing(people):
    from django.contrib.auth.models import AnonymousUser

    q = access.scope_q(AnonymousUser(), MAP)
    assert not User.objects.filter(q).exists()


def test_scoped_queryset_filters_and_requires_scope_map(make_user, people, monkeypatch):
    from django.core.exceptions import ImproperlyConfigured

    qs = ScopedQuerySet(model=User)
    with pytest.raises(ImproperlyConfigured):
        qs.visible_to(make_user("x"))
    monkeypatch.setattr(User, "scope_map", MAP, raising=False)
    o = make_user("officer", "Placement officer")
    services.set_scopes(actor=None, user=o, scopes=[("region", "Kwale")])
    got = ScopedQuerySet(model=User).visible_to(User.objects.get(pk=o.pk))
    assert sorted(got.values_list("username", flat=True)) == ["c", "d"]


# --- API -------------------------------------------------------------------


def api(c, method, url, data=None):
    return (
        getattr(c, method)(url, data, content_type=JSON)
        if data is not None
        else getattr(c, method)(url)
    )


def test_admin_manages_roles_through_the_api(make_user):
    c = Client()
    c.force_login(make_user("a", "Administrator"))
    cat = c.get("/api/v1/identity/permissions").json()
    assert any(p["code"] == "restricted.view_background" and p["grant_only"] for p in cat)
    r = api(
        c,
        "post",
        "/api/v1/identity/roles",
        {"name": "Field agent", "permissions": ["participants.view"]},
    )
    assert r.status_code == 201
    rid = r.json()["id"]
    r = api(
        c,
        "patch",
        f"/api/v1/identity/roles/{rid}",
        {"permissions": ["participants.view", "placements.view"]},
    )
    assert r.json()["permissions"] == ["participants.view", "placements.view"]
    bad = api(
        c, "patch", f"/api/v1/identity/roles/{rid}", {"permissions": ["restricted.view_background"]}
    )
    assert bad.status_code == 400 and any(e["field"] == "permissions" for e in bad.json()["errors"])
    assert api(c, "delete", f"/api/v1/identity/roles/{rid}").status_code == 204
    assert api(c, "get", f"/api/v1/identity/roles/{rid}").status_code == 404
    assert {"role.created", "role.changed", "role.deleted"} <= set(actions())


def test_non_admin_cannot_manage_roles(make_user):
    c = Client()
    c.force_login(make_user("o", "Placement officer"))
    assert c.get("/api/v1/identity/roles").status_code == 403
    assert api(c, "post", "/api/v1/identity/roles", {"name": "X"}).status_code == 403
