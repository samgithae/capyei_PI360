import pytest


@pytest.mark.django_db
def test_health_reports_database(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["database"] == "ok"


@pytest.mark.django_db
def test_me_anonymous_sets_csrf_cookie(client):
    res = client.get("/api/v1/me")
    assert res.status_code == 200
    assert res.json() == {"authenticated": False}
    assert "csrftoken" in res.cookies


def test_me_signed_in_lists_roles_permissions_scope(client, make_user):
    user = make_user("officer", "Placement officer")
    client.force_login(user)
    body = client.get("/api/v1/me").json()
    assert body["authenticated"] is True and body["username"] == "officer"
    assert body["roles"] == ["Placement officer"]
    assert "participants.view" in body["permissions"]
    assert "audit.view" not in body["permissions"]
    assert body["scope"] == {"mode": "assigned", "assignments": []}


def test_argon2_is_default_hasher(settings):
    assert settings.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")
