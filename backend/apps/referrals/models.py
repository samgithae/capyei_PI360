"""Referrals (T-046, FR-16..FR-20): a staff member puts one youth forward for one opportunity.

Stage model from journey J7 (proposed, D-037 pending):

    draft -> submitted -> under_review -> interview (optional)
        -> selected -> placed -> closed
        -> rejected | withdrawn | no_response (need a reason code) -> closed

``Referral`` holds the current state. ``StageEvent`` is the append-only history: every move,
including a correction, adds a row; no row is ever changed or deleted (FR-17, FR-19)."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Referral(models.Model):
    DRAFT, SUBMITTED, UNDER_REVIEW, INTERVIEW = "draft", "submitted", "under_review", "interview"
    SELECTED, PLACED, CLOSED = "selected", "placed", "closed"
    REJECTED, WITHDRAWN, NO_RESPONSE = "rejected", "withdrawn", "no_response"
    STAGES = [
        (DRAFT, "Draft"),
        (SUBMITTED, "Submitted"),
        (UNDER_REVIEW, "Under review"),
        (INTERVIEW, "Interview or assessment"),
        (SELECTED, "Selected"),
        (REJECTED, "Rejected"),
        (WITHDRAWN, "Withdrawn"),
        (NO_RESPONSE, "No response"),
        (PLACED, "Placed"),
        (CLOSED, "Closed"),
    ]
    # Outcomes that need a controlled reason code (FR-18).
    UNSUCCESSFUL = frozenset({REJECTED, WITHDRAWN, NO_RESPONSE})
    # Still in progress: at most one of these per youth and opportunity.
    ACTIVE = frozenset({DRAFT, SUBMITTED, UNDER_REVIEW, INTERVIEW, SELECTED})
    OUTCOMES = {REJECTED, WITHDRAWN, NO_RESPONSE}
    TRANSITIONS = {
        DRAFT: {SUBMITTED, WITHDRAWN},
        SUBMITTED: {UNDER_REVIEW, INTERVIEW, SELECTED} | OUTCOMES,
        UNDER_REVIEW: {INTERVIEW, SELECTED} | OUTCOMES,
        INTERVIEW: {SELECTED} | OUTCOMES,
        SELECTED: {PLACED, WITHDRAWN},
        PLACED: {CLOSED},
        REJECTED: {CLOSED},
        WITHDRAWN: {CLOSED},
        NO_RESPONSE: {CLOSED},
        CLOSED: set(),  # only a correction reopens a closed referral (FR-19)
    }

    OFFICER, TRAINEE = "officer", "trainee"
    # FR-20: one record type for staff referrals and (if D-006/D-007 approve them) trainee
    # applications. Only staff referrals can be created until then.
    ORIGINS = [(OFFICER, "Staff referral"), (TRAINEE, "Trainee application")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(
        "participants.Participant", on_delete=models.PROTECT, related_name="+"
    )
    opportunity = models.ForeignKey(
        "employers.Opportunity", on_delete=models.PROTECT, related_name="+"
    )
    origin = models.CharField(max_length=8, choices=ORIGINS, default=OFFICER)
    stage = models.CharField(max_length=12, choices=STAGES, default=DRAFT, db_index=True)
    reason = models.ForeignKey(
        "configuration.ReferralReason",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    reason_note = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    referred_at = models.DateTimeField(null=True, blank=True)  # set when submitted
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["participant", "opportunity"],
                condition=Q(
                    stage__in=["draft", "submitted", "under_review", "interview", "selected"]
                ),
                name="uniq_active_referral",
            )
        ]

    def __str__(self):
        return f"{self.participant_id} -> {self.opportunity_id} ({self.stage})"


class AppendOnly(Exception):
    pass


class AppendOnlyQuerySet(models.QuerySet):
    """Bulk update and delete would skip the model's own guard, so refuse them here too."""

    def update(self, **kwargs):
        raise AppendOnly("Stage history is append-only.")

    def delete(self):
        raise AppendOnly("Stage history is append-only.")


class StageEvent(models.Model):
    """One stage change. A correction is a new event that points at the event it corrects."""

    TRANSITION, CORRECTION = "transition", "correction"
    KINDS = [(TRANSITION, "Transition"), (CORRECTION, "Correction")]

    id = models.BigAutoField(primary_key=True)
    referral = models.ForeignKey(Referral, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=10, choices=KINDS, default=TRANSITION)
    from_stage = models.CharField(max_length=12, blank=True)  # blank for the first event
    to_stage = models.CharField(max_length=12)
    reason = models.ForeignKey(
        "configuration.ReferralReason",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    note = models.TextField(blank=True)
    corrects = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="corrected_by"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    actor_label = models.CharField(max_length=150)
    at = models.DateTimeField()

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["at", "id"]

    def __str__(self):
        return f"{self.kind}: {self.from_stage or '-'} -> {self.to_stage}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnly("Stage history is append-only; add a correction instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnly("Stage history is append-only; add a correction instead.")
