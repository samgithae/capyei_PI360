import uuid

from django.conf import settings
from django.db import models


class EmployerMember(models.Model):
    """Links a signed-in user to the one employer whose records they may see and act on. A user
    belongs to one employer; an employer has many members. The member's role is the user's
    ordinary role assignment: this table only says *which company*."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employer_member"
    )
    employer = models.ForeignKey("employers.Employer", on_delete=models.PROTECT, related_name="+")
    full_name = models.CharField(max_length=150)
    job_title = models.CharField(max_length=100, blank=True)
    is_owner = models.BooleanField(default=False)  # the first account staff set up
    # The person's record on the employer's contact list. A contact is one person; this member is
    # that person's optional sign-in. Name and job title follow the contact (see ``sync``); the
    # e-mail is the sign-in name, so it stays with the account. PROTECT: a person who can sign in
    # is never removed from the list by accident.
    contact = models.OneToOneField(
        "employers.EmployerContact",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="portal_member",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"employer member {self.pk}"


class EmployerInvite(models.Model):
    """A one-time activation link. Only a hash of the token is stored."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(EmployerMember, on_delete=models.CASCADE, related_name="invites")
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"employer invite {self.pk}"
