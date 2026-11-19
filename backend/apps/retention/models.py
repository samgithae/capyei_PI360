"""Retention tables (doc 05 `retention_policy`, T-073)."""

import uuid

from django.conf import settings
from django.db import models


class RetentionPolicy(models.Model):
    """The period and basis for one data class, and whether it has been approved. Changing the
    period or the basis withdraws the approval, so the job never runs on a rule nobody signed."""

    data_class = models.CharField(max_length=60, unique=True)
    period_days = models.PositiveIntegerField(null=True, blank=True)
    basis = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )  # fmt: skip
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.data_class


class RetentionRun(models.Model):
    """One run of the job, dry or applied. ``results`` holds counts only, never values."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applied = models.BooleanField(default=False)
    actor_label = models.CharField(max_length=150, blank=True)  # username, or "system"
    results = models.JSONField(default=dict)  # {class: {"eligible", "reduced", "skipped"}}
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{'applied' if self.applied else 'dry'} run {self.created_at:%Y-%m-%d %H:%M}"
