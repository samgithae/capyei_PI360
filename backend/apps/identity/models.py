from django.db import models


class LoginLockout(models.Model):
    """Failed sign-in counter per username, kept for unknown usernames too so that lockout
    and its message reveal nothing about which accounts exist."""

    username = models.CharField(max_length=150, unique=True)  # lower-cased
    failures = models.PositiveIntegerField(default=0)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.username}: {self.failures} failures"
