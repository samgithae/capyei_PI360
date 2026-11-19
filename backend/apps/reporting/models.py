"""Export log (doc 05 `export_log`, SEC-15, T-071). One row per export: who, what, how many
rows, which privacy rule was applied. The file itself is kept only until it expires."""

import uuid

from django.conf import settings
from django.db import models


class ExportLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_label = models.CharField(max_length=150)
    dataset = models.CharField(max_length=40)
    file_format = models.CharField(max_length=10)
    filename = models.CharField(max_length=200)
    row_count = models.PositiveIntegerField(default=0)
    withheld_rows = models.PositiveIntegerField(default=0)  # youth left out as too few to show
    suppressed_cells = models.PositiveIntegerField(default=0)
    small_cell_threshold = models.PositiveIntegerField(default=0)
    content = models.BinaryField(null=True, blank=True)  # cleared when the export expires
    downloads = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(
        null=True, blank=True
    )  # none for table exports: nothing is kept
    purged_at = models.DateTimeField(null=True, blank=True)
    # Table exports (identifiable): filters used and stated purpose. The file is not kept.
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.dataset} export {self.created_at:%Y-%m-%d %H:%M}"
