from django.conf import settings
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


class Role(models.Model):
    SCOPE_ALL = "all"
    SCOPE_ASSIGNED = "assigned"
    SCOPE_CHOICES = [(SCOPE_ALL, "Whole organisation"), (SCOPE_ASSIGNED, "Assigned scope only")]

    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=300, blank=True)
    permissions = models.JSONField(default=list)  # codes from catalogue.py
    scope_mode = models.CharField(max_length=10, choices=SCOPE_CHOICES, default=SCOPE_ASSIGNED)
    active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)  # shipped default: cannot be deleted
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class RoleAssignment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_assignments"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="assignments")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="uniq_user_role")]

    def __str__(self):
        return f"{self.user_id}:{self.role_id}"


class ScopeAssignment(models.Model):
    PROGRAMME, COHORT, REGION, OFFICER = "programme", "cohort", "region", "officer"
    KINDS = [(PROGRAMME, "Programme"), (COHORT, "Cohort"), (REGION, "Region"), (OFFICER, "Officer")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scope_assignments"
    )
    kind = models.CharField(max_length=12, choices=KINDS)
    # Reference-data id (as text) until reference tables exist; for "officer" a user id or "self".
    value = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "kind", "value"], name="uniq_user_scope")
        ]

    def __str__(self):
        return f"{self.user_id}:{self.kind}={self.value}"


class PermissionGrant(models.Model):
    """A restricted permission given to one user for a stated purpose, with an expiry."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="permission_grants"
    )
    permission = models.CharField(max_length=60)
    purpose = models.CharField(max_length=300)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user_id}:{self.permission}"
