"""TOTP second factor for privileged roles (SEC-10, ADR-018)."""

from django.conf import settings
from django_otp.plugins.otp_totp.models import TOTPDevice

DEVICE_NAME = "authenticator"


def required_for(user) -> bool:
    if settings.AUTH_MFA_ALL_STAFF or user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name__in=settings.AUTH_MFA_GROUPS).exists()


def confirmed_device(user):
    return TOTPDevice.objects.filter(user=user, confirmed=True).first()


def start_enrolment(user):
    """A fresh unconfirmed device. Replaces any earlier unconfirmed attempt."""
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()
    return TOTPDevice.objects.create(user=user, name=DEVICE_NAME, confirmed=False)


def pending_device(user):
    return TOTPDevice.objects.filter(user=user, confirmed=False).order_by("-pk").first()
