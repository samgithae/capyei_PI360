from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed(sender, **kwargs):
    from .services import ensure_seed_data

    ensure_seed_data()


class ConfigurationConfig(AppConfig):
    name = "apps.configuration"
    label = "configuration"
    verbose_name = "Configuration"

    def ready(self):
        post_migrate.connect(_seed, sender=self)
