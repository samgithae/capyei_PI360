import pytest
from django.contrib.auth.models import Group, User


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


@pytest.mark.django_db
def test_me_signed_in_lists_roles(client):
    user = User.objects.create_user("officer", password="a-long-test-password")
    user.groups.add(Group.objects.create(name="Placement officer"))
    client.force_login(user)
    assert client.get("/api/v1/me").json() == {
        "authenticated": True,
        "username": "officer",
        "roles": ["Placement officer"],
    }


def test_argon2_is_default_hasher(settings):
    assert settings.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")
