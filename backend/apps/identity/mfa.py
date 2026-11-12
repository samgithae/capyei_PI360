"""TOTP second factor for privileged roles (SEC-10, ADR-018)."""

from django.conf import settings
from django_otp.plugins.otp_totp.models import TOTPDevice

DEVICE_NAME = "authenticator"


YOUTH_ONLY = {"youth.self_service"}


def is_youth_only(user) -> bool:
    """A youth account holds nothing but the self-service permission: no staff access to protect
    with a second factor (they would have no authenticator app to enrol)."""
    if user.is_superuser or user.is_staff:
        return False
    roles = list(
        user.role_assignments.filter(role__active=True).values_list("role__permissions", flat=True)
    )
    return bool(roles) and all(set(perms) <= YOUTH_ONLY for perms in roles)


def required_for(user) -> bool:
    if is_youth_only(user):
        return False
    if settings.AUTH_MFA_ALL_STAFF or user.is_superuser or user.is_staff:
        return True
    return user.role_assignments.filter(
        role__active=True, role__name__in=settings.AUTH_MFA_ROLES
    ).exists()


def confirmed_device(user):
    return TOTPDevice.objects.filter(user=user, confirmed=True).first()


def start_enrolment(user):
    """A fresh unconfirmed device. Replaces any earlier unconfirmed attempt."""
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()
    return TOTPDevice.objects.create(user=user, name=DEVICE_NAME, confirmed=False)


def pending_device(user):
    return TOTPDevice.objects.filter(user=user, confirmed=False).order_by("-pk").first()
