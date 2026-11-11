"""Placement history (T-087 stage A, doc 14 §5.3, ADR-020).

One row is one placement episode for one enrollment. A trainee can have several; the import never
overwrites an earlier one. Cross-module links are string references (never imports), so the
module boundary in doc 04 holds. Only the review fields below may change after creation."""

import uuid

from django.conf import settings
from django.db import models


class Placement(models.Model):
    WAGE, SELF, WBL, TRAINING = "wage", "self_employment", "work_based_learning", "further_training"
    PATHWAYS = [
        (WAGE, "Wage employment"),
        (SELF, "Self-employment or entrepreneurship"),
        (WBL, "Work-based learning"),
        (TRAINING, "Further training"),
    ]
    # The only fields a review may change; everything else is the record of what was reported.
    REVIEWABLE = {"employer", "pathway", "status", "verified_by", "verified_on"}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(
        "participants.ParticipantEnrollment",
        on_delete=models.PROTECT,
        related_name="+",
    )
    # Null until a steward links the source name to an employer (stage B, doc 15 §8).
    employer = models.ForeignKey(
        "employers.Employer", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    employer_name_source = models.CharField(max_length=200, blank=True)
    designation = models.CharField(max_length=200, blank=True)
    source_status = models.CharField(max_length=100, blank=True)  # exactly as the source said
    pathway = models.CharField(max_length=25, choices=PATHWAYS, blank=True)  # blank = unmapped
    status = models.CharField(max_length=30, blank=True)  # mapped by stage C; blank = unmapped
    start_date = models.DateField(null=True, blank=True)
    benefits = models.TextField(blank=True)
    source_row = models.ForeignKey(
        "imports.ImportRow", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    verified_on = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-created_at"]
        indexes = [models.Index(fields=["enrollment", "-start_date"])]

    def __str__(self):
        return f"{self.source_status or 'placement'} ({self.id})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            fields = kwargs.get("update_fields")
            if fields is None or not set(fields) <= self.REVIEWABLE:
                raise ValueError("A placement is append-only; only review fields may be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("A placement is append-only and cannot be deleted.")
