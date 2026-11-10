from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_roles(sender, **kwargs):
    from .services import ensure_default_roles

    ensure_default_roles()


class IdentityConfig(AppConfig):
    name = "apps.identity"
    label = "identity"
    verbose_name = "Identity & access"

    def ready(self):
        from apps.api import access

        from .access import IdentityAccess

        access.register(IdentityAccess())
        post_migrate.connect(_seed_roles, sender=self)
