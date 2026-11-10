from django.db import models


class ImmutableError(Exception):
    """Audit rows are append-only (SEC-09)."""


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableError("Audit events cannot be updated.")

    def delete(self):
        raise ImmutableError("Audit events cannot be deleted.")

    def bulk_update(self, *args, **kwargs):
        raise ImmutableError("Audit events cannot be updated.")


class AuditEvent(models.Model):
    """One significant change or decision (doc 05 `audit_event`).

    The actor is stored as an ID and a label, not a foreign key: the audit trail must
    survive user deletion and depends on no other module. ``before`` and ``after`` hold
    only the fields that changed, never whole records, and never secrets.
    """

    at = models.DateTimeField(db_index=True)
    actor_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    actor_label = models.CharField(max_length=150, blank=True)  # username, or "system"
    action = models.CharField(max_length=100, db_index=True)  # e.g. "referral.stage_changed"
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        default_permissions = ("view",)  # nobody "adds", "changes" or "deletes" through roles
        indexes = [models.Index(fields=["object_type", "object_id"])]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.actor_label} {self.action} {self.object_type}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ImmutableError("Audit events cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableError("Audit events cannot be deleted.")
