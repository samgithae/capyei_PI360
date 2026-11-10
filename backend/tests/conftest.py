import pytest
from django.contrib.auth.models import User

from apps.identity import services


@pytest.fixture
def make_user(db):
    """make_user("amina", "Placement officer") -> a user holding that shipped role."""
    services.ensure_default_roles()

    def _make(username, role=None, **kw):
        user = User.objects.create_user(
            username, f"{username}@example.org", "a-long-test-password", **kw
        )
        if role:
            from apps.identity.models import Role

            services.assign_role(actor=None, user=user, role=Role.objects.get(name=role))
        return user

    return _make
