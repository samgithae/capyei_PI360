"""Authorisation matrix harness (T-035, SEC-06): every API route is classified, and each
classification is checked against every role. A new route without an entry fails the build."""

import pytest
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver

from apps.identity.defaults import DEFAULT_ROLES

PUBLIC = "public"  # reachable without signing in
SIGNED_IN = "signed_in"  # any signed-in user

# route (without the api/v1/ prefix) -> {HTTP method: PUBLIC | SIGNED_IN | permission code}
MATRIX = {
    "health": {"GET": PUBLIC},
    "me": {"GET": PUBLIC},
    "schema/": {"GET": PUBLIC},
    "auth/login": {"POST": PUBLIC},
    "auth/logout": {"POST": PUBLIC},
    "auth/mfa/setup": {"POST": PUBLIC},
    "auth/mfa/confirm": {"POST": PUBLIC},
    "auth/mfa/verify": {"POST": PUBLIC},
    "auth/password/reset": {"POST": PUBLIC},
    "auth/password/reset/confirm": {"POST": PUBLIC},
    "auth/password/change": {"POST": SIGNED_IN},
    "identity/permissions": {"GET": "identity.manage_roles"},
    "identity/roles": {"GET": "identity.manage_roles", "POST": "identity.manage_roles"},
    "identity/roles/<int:pk>": {
        "GET": "identity.manage_roles",
        "PATCH": "identity.manage_roles",
        "DELETE": "identity.manage_roles",
    },
    "identity/users": {"GET": "identity.view_users", "POST": "identity.manage_users"},
    "identity/users/<int:pk>": {"GET": "identity.view_users", "PATCH": "identity.manage_users"},
    "identity/users/<int:pk>/suspend": {"POST": "identity.manage_users"},
    "identity/users/<int:pk>/reactivate": {"POST": "identity.manage_users"},
    "identity/users/<int:pk>/reset-mfa": {"POST": "identity.manage_users"},
    "identity/users/<int:pk>/roles": {"PUT": "identity.manage_roles"},
    "identity/users/<int:pk>/scopes": {"PUT": "identity.manage_roles"},
    "audit/events": {"GET": "audit.view"},
    "retention": {"GET": "retention.view"},
    "retention/run": {"POST": "retention.manage"},
    "retention/<str:code>": {"PUT": "retention.manage"},
    "retention/<str:code>/approve": {"POST": "retention.manage"},
    "retention/<str:code>/revoke": {"POST": "retention.manage"},
    "participants/skills": {"GET": "participants.view_profile"},
    "participants/skills/categories": {"GET": "participants.view_profile"},
    "participants/skills/popular": {"GET": "participants.view_profile"},
    "participants/skills/add": {"POST": "participants.edit"},
    "participants/profile-options": {"GET": "participants.edit"},
    "config/reference/cohort-courses/bulk": {"POST": "reference.manage"},
    "config/reference/<str:kind>": {"GET": "config.view", "POST": "reference.manage"},
    "config/reference/<str:kind>/import": {"POST": "reference.manage"},
    "config/reference/<str:kind>/import-template": {"GET": "config.view"},
    "config/reference/<str:kind>/<uuid:pk>": {"GET": "config.view", "PATCH": "reference.manage"},
    "config/reference/<str:kind>/<uuid:pk>/deactivate": {"POST": "reference.manage"},
    "config/reference/<str:kind>/<uuid:pk>/reactivate": {"POST": "reference.manage"},
    "config/reference/<str:kind>/<uuid:pk>/aliases": {"POST": "reference.manage"},
    "config/places/<str:kind>": {"GET": SIGNED_IN},
    "config/flags": {"GET": "config.view"},
    "config/flags/<str:key>": {"PATCH": "config.manage"},
    "config/settings": {"GET": "config.view", "POST": "config.manage_protected"},
    "participants/filters": {"GET": "participants.view"},
    "participants": {"GET": "participants.view", "POST": "participants.edit"},
    "participants/check-name": {"GET": "participants.edit"},
    "participants/<uuid:pk>": {
        "GET": "participants.view",
        "PATCH": "participants.edit",
        "DELETE": "records.archive",
    },
    "participants/<uuid:pk>/enrollments": {"POST": "participants.edit"},
    "participants/<uuid:pk>/enrollments/<uuid:enrollment_id>": {"PATCH": "participants.edit"},
    "participants/<uuid:pk>/contacts": {"PUT": "participants.edit"},
    "participants/<uuid:pk>/consent": {"PUT": "participants.edit"},
    "participants/<uuid:pk>/invite": {
        "GET": "participants.invite",
        "POST": "participants.invite",
        "DELETE": "participants.invite",
    },
    "employer/activate/check": {"POST": PUBLIC},
    "employer/activate": {"POST": PUBLIC},
    "employer/me": {"GET": "employer.portal"},
    "employer/roles": {"GET": "employer.manage_staff"},
    "employer/people": {"GET": "employer.view_profile"},
    "employer/logo": {
        "GET": "employer.view_profile",
        "POST": "employer.edit_profile",
        "DELETE": "employer.edit_profile",
    },
    "employer/staff": {"GET": "employer.manage_staff", "POST": "employer.manage_staff"},
    "employer/staff/<uuid:mpk>": {
        "PATCH": "employer.manage_staff",
        "DELETE": "employer.manage_staff",
    },
    "employer/dashboard": {"GET": "employer.view_dashboard"},
    "employer/profile": {"GET": "employer.view_profile", "PATCH": "employer.edit_profile"},
    "employer/contacts": {"POST": "employer.edit_profile"},
    "employer/contacts/<uuid:cpk>": {
        "PATCH": "employer.edit_profile",
        "DELETE": "employer.edit_profile",
    },
    "employer/opportunities": {
        "GET": "employer.view_opportunities",
        "POST": "employer.edit_opportunities",
    },
    "employer/opportunities/<uuid:pk>": {
        "GET": "employer.view_opportunities",
        "PATCH": "employer.edit_opportunities",
    },
    "employer/opportunities/<uuid:pk>/transition": {"POST": "employer.publish_opportunities"},
    "employer/opportunities/<uuid:pk>/requirements": {"POST": "employer.edit_opportunities"},
    "employer/opportunities/<uuid:pk>/requirements/skills": {"PUT": "employer.edit_opportunities"},
    "employer/opportunities/<uuid:pk>/requirements/<uuid:rpk>": {
        "PATCH": "employer.edit_opportunities",
        "DELETE": "employer.edit_opportunities",
    },
    "employer/skills": {"GET": "employer.view_opportunities"},
    "employer/skills/categories": {"GET": "employer.view_opportunities"},
    "employer/skills/popular": {"GET": "employer.view_opportunities"},
    "employer/referrals": {"GET": "employer.view_referrals"},
    "employer/referral-reasons": {"GET": "employer.view_referrals"},
    "employer/referrals/<uuid:pk>": {"GET": "employer.view_referrals"},
    "employer/referrals/<uuid:pk>/transition": {"POST": "employer.respond_referrals"},
    "employer/referrals/<uuid:pk>/interview": {"POST": "employer.respond_referrals"},
    "employer/referrals/<uuid:pk>/cv": {"GET": "employer.view_referrals"},
    "employer/referrals/<uuid:pk>/cv.pdf": {"GET": "employer.view_referrals"},
    "employer/referrals/<uuid:pk>/photo": {"GET": "employer.view_referrals"},
    "employer/referrals/<uuid:pk>/why": {"GET": "employer.view_referrals"},
    "opportunities/<uuid:pk>/publish-decline": {"POST": "employers.edit"},
    "employers/<uuid:pk>/people": {"GET": "employers.view"},
    "employers/<uuid:pk>/users": {"GET": "employers.view", "POST": "employers.invite_user"},
    "employers/<uuid:pk>/users/<uuid:mpk>": {
        "PATCH": "employers.invite_user",
        "DELETE": "employers.invite_user",
    },
    "youth/activate/check": {"POST": PUBLIC},
    "youth/activate": {"POST": PUBLIC},
    "youth/me": {"GET": "youth.self_service"},
    "youth/consent": {"POST": "youth.self_service"},
    "youth/profile": {"PUT": "youth.self_service"},
    "youth/details": {"PUT": "youth.self_service"},
    "youth/skills": {"GET": "youth.self_service"},
    "youth/skills/categories": {"GET": "youth.self_service"},
    "youth/skills/popular": {"GET": "youth.self_service"},
    "youth/skills/add": {"POST": "youth.self_service"},
    "youth/cv": {"GET": "youth.self_service"},
    "youth/cv.pdf": {"GET": "youth.self_service"},
    "youth/photo": {
        "GET": "youth.self_service",
        "POST": "youth.self_service",
        "DELETE": "youth.self_service",
    },
    "youth/journey": {"GET": "youth.self_service"},
    "youth/notices": {"GET": "youth.self_service", "POST": "youth.self_service"},
    "youth/placement": {"GET": "youth.self_service"},
    "youth/opportunities/<uuid:pk>": {"GET": "youth.self_service"},
    "participants/<uuid:pk>/residence": {"PUT": "participants.edit"},
    "participants/<uuid:pk>/profile": {
        "GET": "participants.view_profile",
        "PUT": "participants.edit",
    },
    "participants/<uuid:pk>/profile/verify": {"POST": "participants.edit"},
    "participants/<uuid:pk>/verification": {"POST": "participants.edit"},
    "participants/<uuid:pk>/activity": {"GET": "participants.view_profile"},
    "participants/<uuid:pk>/cv": {"GET": "participants.view_profile"},
    "participants/<uuid:pk>/cv.pdf": {"GET": "participants.view_profile"},
    "participants/<uuid:pk>/photo": {
        "GET": "participants.view_profile",
        "POST": "participants.edit",
        "DELETE": "participants.edit",
    },
    "participants/profile-import": {"POST": "participants.edit"},
    "participants/profile-import-template": {"GET": "participants.edit"},
    "participants/archive": {"POST": "records.archive"},
    "participants/restore": {"POST": "records.archive"},
    "participants/duplicates": {"GET": "duplicates.review"},
    "participants/duplicates/scan": {"POST": "duplicates.review"},
    "participants/duplicates/<uuid:pk>/dismiss": {"POST": "duplicates.review"},
    "participants/duplicates/<uuid:pk>/merge": {"POST": "duplicates.merge"},
    "participants/data-quality": {"GET": "dataquality.review"},
    "participants/data-quality/records": {"GET": "dataquality.review"},
    "participants/corrections": {"GET": "dataquality.review"},
    "participants/corrections/<uuid:pk>/resolve": {"POST": "dataquality.review"},
    "participants/merges": {"GET": "duplicates.review"},
    "participants/merges/<uuid:pk>/undo": {"POST": "duplicates.merge"},
    "employers": {"GET": "employers.view", "POST": "employers.edit"},
    "employers/filters": {"GET": "employers.view"},
    "employers/check-name": {"GET": "employers.edit"},
    "employers/<uuid:pk>": {
        "GET": "employers.view",
        "PATCH": "employers.edit",
        "DELETE": "records.archive",
    },
    "employers/archive": {"POST": "records.archive"},
    "employers/restore": {"POST": "records.archive"},
    "employers/<uuid:pk>/history": {"GET": "employers.view"},
    "employers/<uuid:pk>/contacts": {"POST": "employers.edit"},
    "employers/<uuid:pk>/contacts/<uuid:cpk>": {
        "PATCH": "employers.edit",
        "DELETE": "employers.edit",
    },
    "interventions": {"GET": "referrals.view", "POST": "referrals.edit"},
    "interventions/options": {"GET": "referrals.view"},
    "interventions/<uuid:pk>": {"GET": "referrals.view", "PATCH": "referrals.edit"},
    "interventions/<uuid:pk>/move": {"POST": "referrals.edit"},
    "interventions/<uuid:pk>/assign": {"POST": "caseload.reassign"},
    "interventions/<uuid:pk>/history": {"GET": "referrals.view"},
    "cases/queue": {"GET": "referrals.view"},
    "placements": {"GET": "placements.view", "POST": "placements.edit"},
    "placements/summary": {"GET": "placements.view"},
    "placements/options": {"GET": "placements.view"},
    "placements/<uuid:pk>": {"GET": "placements.view", "PATCH": "placements.edit"},
    "placements/<uuid:pk>/end": {"POST": "placements.edit"},
    "placements/<uuid:pk>/verify": {"POST": "placements.edit"},
    "placements/<uuid:pk>/history": {"GET": "placements.view"},
    "followups": {"GET": "placements.view"},
    "followups/summary": {"GET": "placements.view"},
    "followups/options": {"GET": "placements.view"},
    "followups/steps": {"GET": "config.view", "POST": "config.manage"},
    "followups/steps/<uuid:pk>": {"PATCH": "config.manage"},
    "followups/<uuid:pk>": {"GET": "placements.view"},
    "followups/<uuid:pk>/history": {"GET": "placements.view"},
    "followups/<uuid:pk>/attempts": {"POST": "placements.edit"},
    "followups/<uuid:pk>/complete": {"POST": "placements.edit"},
    "followups/<uuid:pk>/unreachable": {"POST": "placements.edit"},
    "followups/<uuid:pk>/cancel": {"POST": "placements.edit"},
    "followups/<uuid:pk>/assign": {"POST": "caseload.reassign"},
    "referrals/bulk": {"POST": "referrals.edit"},
    "referrals/by-opportunity": {"GET": "referrals.view"},
    "referrals": {"GET": "referrals.view", "POST": "referrals.edit"},
    "referrals/summary": {"GET": "referrals.view"},
    "referrals/reasons": {"GET": "referrals.view"},
    "referrals/assignees": {"GET": "caseload.reassign"},
    "referrals/<uuid:pk>": {"GET": "referrals.view"},
    "referrals/<uuid:pk>/transition": {"POST": "referrals.edit"},
    "referrals/<uuid:pk>/interview": {"PUT": "referrals.edit"},
    "referrals/<uuid:pk>/correct": {"POST": "referrals.view"},  # + stage check in view
    "referrals/<uuid:pk>/assign": {"POST": "caseload.reassign"},
    "referrals/<uuid:pk>/history": {"GET": "referrals.view"},
    "opportunities/<uuid:pk>/suggestions": {"GET": "participants.view_profile"},
    "referrals/<uuid:pk>/fit": {"GET": "referrals.view"},
    "rules": {"GET": "intelligence.view", "POST": "intelligence.manage_rules"},
    "rules/operators": {"GET": "intelligence.view"},
    "employers/<uuid:pk>/evidence": {"GET": "intelligence.view"},
    "employers/<uuid:pk>/feedback": {"GET": "employers.view", "POST": "employers.edit"},
    "employers/<uuid:pk>/feedback/<uuid:cpk>": {"DELETE": "employers.edit"},
    "support/queue": {"GET": "participants.view_profile"},
    "reporting/dashboard": {"GET": SIGNED_IN},
    "reporting/drilldown": {"GET": SIGNED_IN},
    "identity/grants": {"GET": "identity.manage_roles", "POST": "identity.manage_roles"},
    "identity/grants/<int:pk>/revoke": {"POST": "identity.manage_roles"},
    "exports": {"GET": "exports.deidentified", "POST": "exports.deidentified"},
    "exports/table/<slug:table>": {"POST": "exports.identifiable"},
    "exports/fields/<slug:table>": {"GET": "exports.identifiable"},
    "exports/<uuid:pk>/download": {"GET": "exports.deidentified"},
    "participants/<uuid:pk>/support-review": {"POST": "referrals.edit"},
    "rules/settings": {"GET": "intelligence.view", "PUT": "intelligence.manage_rules"},
    "rules/<uuid:pk>": {"GET": "intelligence.view"},
    "rules/versions/<uuid:pk>": {
        "GET": "intelligence.view",
        "PATCH": "intelligence.manage_rules",
        "DELETE": "intelligence.manage_rules",
    },
    "rules/versions/<uuid:pk>/clone": {"POST": "intelligence.manage_rules"},
    "rules/versions/<uuid:pk>/submit": {"POST": "intelligence.manage_rules"},
    "rules/versions/<uuid:pk>/return": {"POST": "intelligence.approve_rules"},
    "rules/versions/<uuid:pk>/approve": {"POST": "intelligence.approve_rules"},
    "rules/versions/<uuid:pk>/activate": {"POST": "intelligence.approve_rules"},
    "rules/versions/<uuid:pk>/deactivate": {"POST": "intelligence.approve_rules"},
    "rules/versions/<uuid:pk>/history": {"GET": "intelligence.view"},
    "opportunities": {"GET": "employers.view", "POST": "employers.edit"},
    "opportunities/<uuid:pk>": {
        "GET": "employers.view",
        "PATCH": "employers.edit",
        "DELETE": "records.archive",
    },
    "opportunities/archive": {"POST": "records.archive"},
    "opportunities/restore": {"POST": "records.archive"},
    "opportunities/<uuid:pk>/transition": {"POST": "employers.edit"},
    "opportunities/<uuid:pk>/history": {"GET": "employers.view"},
    "requirement-skills": {"GET": "employers.view"},
    "requirement-skills/categories": {"GET": "employers.view"},
    "requirement-skills/popular": {"GET": "employers.view"},
    "requirement-skills/add": {"POST": "employers.edit"},
    "opportunities/<uuid:pk>/requirements": {"POST": "employers.edit"},
    "opportunities/<uuid:pk>/requirements/skills": {"PUT": "employers.edit"},
    "opportunities/<uuid:pk>/requirements/<uuid:rpk>": {
        "PATCH": "employers.edit",
        "DELETE": "employers.edit",
    },
    "imports/templates": {"GET": "imports.run", "POST": "imports.run"},
    "imports/inspect": {"POST": "imports.run"},
    "imports/sample": {"GET": "imports.run"},
    "imports/batches": {"GET": "imports.run", "POST": "imports.run"},
    "imports/batches/<uuid:pk>": {"GET": "imports.run"},
    "imports/batches/<uuid:pk>/rows": {"GET": "imports.run"},
    "imports/batches/<uuid:pk>/errors": {"GET": "imports.run"},
    "imports/batches/<uuid:pk>/reconciliation": {"GET": "imports.run"},
    "imports/templates/<uuid:pk>/contract": {"GET": "imports.run"},
    "imports/batches/<uuid:pk>/review": {"GET": "imports.run"},
    "imports/batches/<uuid:pk>/review/employers": {"POST": "imports.commit"},
    "imports/batches/<uuid:pk>/review/statuses": {"POST": "imports.commit"},
    "imports/batches/<uuid:pk>/review/statuses/proposed": {"POST": "imports.commit"},
    "imports/extra": {"GET": "imports.run"},
    "imports/extra/promote": {"POST": "imports.commit"},
    "imports/batches/<uuid:pk>/recheck": {"POST": "imports.commit"},
    "imports/batches/<uuid:pk>/approve": {"POST": "imports.commit"},
    "imports/batches/<uuid:pk>/commit": {"POST": "imports.commit"},
    "imports/batches/<uuid:pk>/rollback": {"POST": "imports.commit"},
    "imports/batches/<uuid:pk>/signoff": {"GET": "imports.run", "POST": "imports.commit"},
    "imports/batches/<uuid:pk>/cancel": {"POST": "imports.run"},
}


def routes(resolver=None, prefix=""):
    resolver = resolver or get_resolver()
    for p in resolver.url_patterns:
        text = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from routes(p, text)
        elif isinstance(p, URLPattern):
            yield text


def api_routes():
    return sorted(r.removeprefix("api/v1/") for r in routes() if r.startswith("api/v1/"))


def test_every_route_is_in_the_matrix():
    assert set(api_routes()) == set(MATRIX), "classify new routes in tests/test_authz_matrix.py"


def concrete(route):
    return "/api/v1/" + (
        route.replace("<uuid:cpk>", "00000000-0000-0000-0000-000000000001")
        .replace("<uuid:rpk>", "00000000-0000-0000-0000-000000000002")
        .replace("<uuid:enrollment_id>", "00000000-0000-0000-0000-000000000003")
        .replace("<uuid:mpk>", "00000000-0000-0000-0000-000000000004")
        .replace("<int:pk>", "999999")
        .replace("<uuid:pk>", "00000000-0000-0000-0000-000000000000")
        .replace("<str:kind>", "sectors")
        .replace("<str:key>", "x")
        .replace("<slug:table>", "youth")
    )


ROLES = [r["name"] for r in DEFAULT_ROLES if r["active"]]
CASES = [(route, method, rule) for route, rules in MATRIX.items() for method, rule in rules.items()]


def call(client, method, route):
    url = concrete(route)
    if method == "GET":
        return client.get(url)
    return getattr(client, method.lower())(url, {}, content_type="application/json")


@pytest.mark.parametrize("route,method,rule", CASES)
def test_anonymous(route, method, rule):
    status = call(Client(), method, route).status_code
    if rule == PUBLIC:
        assert status not in (401, 403), (route, method, status)
    else:
        assert status == 401, (route, method, status)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("route,method,rule", CASES)
def test_each_role(make_user, role, route, method, rule):
    allowed = {r["name"]: set(r["permissions"]) for r in DEFAULT_ROLES}[role]
    c = Client()
    c.force_login(make_user("u", role))
    status = call(c, method, route).status_code
    if rule in (PUBLIC, SIGNED_IN) or rule in allowed:
        assert status != 403 and status != 401, (role, route, method, status)
    else:
        assert status == 403, (role, route, method, status)


@pytest.mark.parametrize("route,method,rule", CASES)
def test_signed_in_user_with_no_role_gets_only_public_and_signed_in(make_user, route, method, rule):
    c = Client()
    c.force_login(make_user("norole"))
    status = call(c, method, route).status_code
    if rule in (PUBLIC, SIGNED_IN):
        assert status not in (401, 403)
    else:
        assert status == 403


def test_every_permission_in_the_matrix_exists():
    from apps.identity.catalogue import BY_CODE

    for rules in MATRIX.values():
        for rule in rules.values():
            assert rule in (PUBLIC, SIGNED_IN) or rule in BY_CODE
