from django.apps import AppConfig


class EmployerPortalConfig(AppConfig):
    name = "apps.employer_portal"
    label = "employer_portal"
    verbose_name = "Employer portal"

    def ready(self):
        from apps.api import access

        from . import sync
        from .services import mfa_required

        access.register_mfa_policy(mfa_required)
        sync.connect()
