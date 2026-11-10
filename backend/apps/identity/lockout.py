"""Account lockout after repeated failed sign-ins (FR-01, SEC-10)."""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import LoginLockout


def _key(username: str) -> str:
    return username.strip().lower()[:150]


def locked_seconds(username: str) -> int:
    """Seconds left on a lockout, or 0 if the account may try."""
    row = LoginLockout.objects.filter(username=_key(username)).first()
    if row and row.locked_until and row.locked_until > timezone.now():
        return int((row.locked_until - timezone.now()).total_seconds()) + 1
    return 0


def register_failure(username: str) -> bool:
    """Count a failure. Returns True when this failure triggers the lockout."""
    now = timezone.now()
    window = timedelta(seconds=settings.AUTH_LOCKOUT_SECONDS)
    with transaction.atomic():
        row, _ = LoginLockout.objects.select_for_update().get_or_create(username=_key(username))
        if row.last_failure_at and now - row.last_failure_at > window:
            row.failures = 0  # old failures expire
        row.failures += 1
        row.last_failure_at = now
        newly_locked = row.failures >= settings.AUTH_MAX_FAILURES
        if newly_locked:
            row.locked_until = now + window
            row.failures = 0
        row.save()
    return newly_locked


def clear(username: str) -> None:
    LoginLockout.objects.filter(username=_key(username)).delete()
