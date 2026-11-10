"""Import pipeline tables (T-040, doc 05 §6.1)."""

import uuid

from django.conf import settings
from django.db import models


class MappingTemplate(models.Model):
    """A versioned mapping from a source layout to target fields. Versions are never edited: a
    change is a new version, so a batch always points at the exact mapping it used."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=60)  # e.g. "go-blue-trainees"
    version = models.PositiveIntegerField()
    target = models.CharField(max_length=30, default="participants")
    columns = models.JSONField()  # {"source column header": "target field"}
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "version"], name="uniq_template_version")
        ]

    def __str__(self):
        return f"{self.source} v{self.version}"


class ImportBatch(models.Model):
    UPLOADED, VALIDATED, APPROVED, COMMITTING = "uploaded", "validated", "approved", "committing"
    COMMITTED, PARTIAL, REJECTED, ROLLED_BACK, CANCELLED = (
        "committed",
        "partially_committed",
        "rejected",
        "rolled_back",
        "cancelled",
    )
    STATUSES = [
        (s, s.replace("_", " ").capitalize())
        for s in (UPLOADED, VALIDATED, APPROVED, COMMITTING, COMMITTED, PARTIAL, REJECTED,
                  ROLLED_BACK, CANCELLED)
    ]  # fmt: skip

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(MappingTemplate, on_delete=models.PROTECT, related_name="batches")
    file_name = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64, db_index=True)  # sha-256 of the uploaded bytes
    status = models.CharField(max_length=20, choices=STATUSES, default=UPLOADED)
    counts = models.JSONField(default=dict)
    defaults = models.JSONField(default=dict)  # cohort defaults used for empty cells (doc 15 §3)
    duplicate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.file_name} ({self.status})"


class ImportRow(models.Model):
    """One source row. ``raw`` is the file's own text (real data in production: it is subject to
    the retention setting); ``clean`` is the normalised form the target receives."""

    NEW, EXACT = "new", "exact"
    CREATE, UPDATE, HELD, SKIP = "create", "update", "held", "skip"

    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_no = models.PositiveIntegerField()  # 1-based position in the file's data rows
    row_hash = models.CharField(max_length=64)
    source_key = models.CharField(max_length=200, blank=True)
    raw = models.JSONField()
    clean = models.JSONField(default=dict)
    match = models.CharField(max_length=10, default=NEW)
    outcome = models.CharField(max_length=10, default=CREATE)
    errors = models.JSONField(default=list)
    warnings = models.JSONField(default=list)
    committed = models.BooleanField(default=False)
    record_id = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["batch", "row_no"], name="uniq_row_per_batch")
        ]
        indexes = [models.Index(fields=["batch", "outcome"])]

    def __str__(self):  # never print raw values: they may be personal data
        return f"row {self.row_no}"


class RecordLineage(models.Model):
    """Which batch row created or changed which record, with the values before and after."""

    id = models.BigAutoField(primary_key=True)
    row = models.ForeignKey(ImportRow, on_delete=models.CASCADE, related_name="lineage")
    entity = models.CharField(max_length=30)
    record_id = models.CharField(max_length=40, db_index=True)
    action = models.CharField(max_length=10)  # create | update
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    reverted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} {self.entity} {self.record_id}"


class ReconciliationSignoff(models.Model):
    """The data owner's sign-off on a loaded batch's reconciliation (T-053). One per batch; it is
    never edited. The signer is a named person at CAP-YEI and need not have a PI360 account, so
    we keep their name and role as text and who recorded it as a user."""

    batch = models.OneToOneField(ImportBatch, on_delete=models.PROTECT, related_name="signoff")
    signer_name = models.CharField(max_length=120)
    signer_role = models.CharField(max_length=120)
    signed_on = models.DateField()
    note = models.TextField(blank=True)
    snapshot = models.JSONField(default=dict)  # the reconciliation as it stood when signed
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"signed off by {self.signer_name}"
