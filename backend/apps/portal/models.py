import uuid

from django.conf import settings
from django.db import models


class YouthAccount(models.Model):
    """Links a signed-in user to the one participant record they may see and edit. One account
    per participant, one participant per account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="youth_account"
    )
    participant = models.OneToOneField(
        "participants.Participant", on_delete=models.PROTECT, related_name="youth_account"
    )
    consent_version = models.CharField(max_length=20, blank=True)
    consented_at = models.DateTimeField(null=True, blank=True)
    notices_seen_at = models.DateTimeField(null=True, blank=True)  # updates read up to here
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"youth account {self.pk}"


class YouthInvite(models.Model):
    """A one-time activation link. Only a hash of the token is stored."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(YouthAccount, on_delete=models.CASCADE, related_name="invites")
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"invite {self.pk}"


class RegistrationRequest(models.Model):
    """A youth's self-registration, held apart from the participant records (NEW-044, D-083).

    Nothing here is copied to a Participant until a steward approves it or links it to an
    existing record. Only hashes of the e-mail token and the phone code are kept, and no raw IP
    address (only a salted hash, to spot abuse)."""

    PENDING, VERIFIED, REVIEW = "pending_verification", "verified", "under_review"
    APPROVED, LINKED, REJECTED, EXPIRED = "approved_new", "linked_existing", "rejected", "expired"
    STATUS_CHOICES = [
        (PENDING, "Waiting for verification"),
        (VERIFIED, "Verified"),
        (REVIEW, "Needs review"),
        (APPROVED, "Approved as new youth"),
        (LINKED, "Linked to an existing record"),
        (REJECTED, "Rejected"),
        (EXPIRED, "Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    given_name = models.CharField(max_length=100)
    family_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    claimed_programme_code = models.CharField(max_length=40, blank=True)
    claimed_enrollment_no = models.CharField(max_length=60, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    verify_token_hash = models.CharField(max_length=64, blank=True)
    verify_expires_at = models.DateTimeField(null=True, blank=True)
    otp_hash = models.CharField(max_length=64, blank=True)
    otp_attempts = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=PENDING)
    possible_duplicate = models.BooleanField(default=False)
    participant = models.ForeignKey(
        "participants.Participant", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )  # fmt: skip
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )  # fmt: skip
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True)
    consent_version = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"registration {self.pk}"
