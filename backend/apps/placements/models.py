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
    # How an episode was confirmed (FR-23). Working list, D-011.
    SOURCES = [
        ("employer_confirmation", "Employer confirmation"),
        ("document", "Document (contract, letter, licence)"),
        ("phone_call", "Phone call with the youth or employer"),
        ("site_visit", "Site visit"),
        ("other", "Other"),
    ]
    # The only fields a review may change; everything else is the record of what was reported.
    # ``start_date`` and ``designation`` may be corrected only on an episode a staff member
    # entered by hand (see services.update_episode); an imported one stays as reported.
    REVIEWABLE = {
        "employer", "pathway", "status", "verified_by", "verified_on",
        "end_date", "exit_reason", "verification_source",
        "start_date", "designation", "employer_name_source", "benefits",
    }  # fmt: skip

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
    # FR-24: an episode ends; a later one is added beside it, never over it.
    end_date = models.DateField(null=True, blank=True)
    exit_reason = models.CharField(max_length=200, blank=True)
    verification_source = models.CharField(max_length=25, choices=SOURCES, blank=True)
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


class PlacementStatusMapping(models.Model):
    """What a source "placement status" value means (T-087 stage C, doc 14 §6, D-061).

    Data, not code: stewards change it without a release. Ships empty; until a value is mapped,
    rows carrying it stay held and nothing is derived. ``is_placement`` False marks a value that
    is a referral outcome (e.g. an offer declined), not a placement."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_value = models.CharField(max_length=100)  # as first mapped, for display
    source_key = models.CharField(max_length=100, unique=True, editable=False)
    pathway = models.CharField(max_length=25, choices=Placement.PATHWAYS, blank=True)
    status = models.CharField(max_length=30)
    is_placement = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    mapped_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    mapped_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_value"]

    def __str__(self):
        return f"{self.source_value} -> {self.status}"


class FollowUpStep(models.Model):
    """One line of the follow-up schedule (T-066, FR-25, D-012/D-028): "check in N days after the
    placement started". Data, not code: an administrator changes the schedule without a release.

    A step is a template only. When a placement is confirmed each active step becomes a
    ``FollowUp`` that carries its own copy of the label and due date, so changing or switching
    off a step never moves, deletes or re-labels a task that already exists."""

    EARLY, TRACER = "early", "tracer"
    KINDS = [(EARLY, "Early follow-up"), (TRACER, "Tracer follow-up")]
    MAX_DAYS = 732  # 24 months (BR-10)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=10, choices=KINDS)
    label = models.CharField(max_length=60)
    offset_days = models.PositiveIntegerField()
    active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["offset_days", "label"]

    def __str__(self):
        return f"{self.label} ({self.offset_days} days)"


class FollowUp(models.Model):
    """A check-in with a placed youth, due on a date (T-066, FR-25/FR-26).

    Never deleted: a task nobody will do is cancelled with a reason. ``due_date``, ``kind`` and
    ``label`` are copied from the step when the task is generated. Every change is audited."""

    OPEN, DONE, UNREACHABLE, CANCELLED = "open", "done", "unreachable", "cancelled"
    STATUSES = [
        (OPEN, "Open"),
        (DONE, "Done"),
        (UNREACHABLE, "Could not be reached"),
        (CANCELLED, "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    placement = models.ForeignKey(Placement, on_delete=models.PROTECT, related_name="followups")
    step = models.ForeignKey(
        FollowUpStep, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    kind = models.CharField(max_length=10, choices=FollowUpStep.KINDS)
    label = models.CharField(max_length=60)
    due_date = models.DateField()
    status = models.CharField(max_length=12, choices=STATUSES, default=OPEN)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # What the check-in found, set when it is completed (FR-25: response, evidence).
    still_employed = models.BooleanField(null=True, blank=True)
    evidence_source = models.CharField(max_length=25, choices=Placement.SOURCES, blank=True)
    response_note = models.TextField(blank=True)
    # What happens next, if anything; the latest attempt sets it (FR-25: next action).
    next_action = models.CharField(max_length=200, blank=True)
    next_action_date = models.DateField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "created_at"]
        constraints = [
            # One task per placement per step: generating twice never doubles the work.
            models.UniqueConstraint(fields=["placement", "step"], name="one_followup_per_step")
        ]
        indexes = [models.Index(fields=["status", "due_date"])]

    def __str__(self):
        return f"{self.label} due {self.due_date}"

    def delete(self, *args, **kwargs):
        raise ValueError("A follow-up is never deleted; cancel it with a reason.")


class FollowUpAttempt(models.Model):
    """One try at reaching the youth (or employer) for a follow-up. Append-only."""

    METHODS = [
        ("phone", "Phone call"),
        ("sms", "SMS"),
        ("whatsapp", "WhatsApp"),
        ("email", "Email"),
        ("visit", "Visit"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    followup = models.ForeignKey(FollowUp, on_delete=models.PROTECT, related_name="attempts")
    method = models.CharField(max_length=10, choices=METHODS)
    reached = models.BooleanField()
    made_on = models.DateField()
    note = models.TextField(blank=True)
    made_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-made_on", "-created_at"]

    def __str__(self):
        return f"{self.get_method_display()} on {self.made_on}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("A follow-up attempt is append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("A follow-up attempt is append-only and cannot be deleted.")
