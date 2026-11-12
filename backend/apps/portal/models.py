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
