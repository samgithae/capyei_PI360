"""Youth portal (Phase 2): a youth signs in to their own record, once staff have invited them.

Staff invite to an e-mail address already on the record; there is no open registration. The link
is single-use and expires. A youth sees and edits only their own capability profile, after
accepting the data-use notice. Entries they make are marked self-reported until staff verify them.

This module coordinates identity (accounts, roles) and participants (the record); neither knows
about the other.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import mail
from django.db import transaction
from django.utils import timezone

from apps.api import access
from apps.audit import services as audit
from apps.identity import services as identity
from apps.participants import services as participants

from .models import YouthAccount, YouthInvite

ROLE = "Youth"
SELF_SERVICE = "youth.self_service"
INVITE_DAYS = 7
CONSENT_VERSION = "2026-11-v1"
# DRAFT wording for the data-protection officer to review before pilot use (see
# docs/data-protection-review.md). Changing the text means changing CONSENT_VERSION, which asks
# every youth to accept again.
CONSENT_TEXT = (
    "CAP-YEI Placement Intelligence 360 helps your officer match you to job, training and "
    "attachment opportunities. If you continue, you can view and add your qualifications, skills, "
    "work experience and availability. Staff who work on your placement can see what you enter; "
    "it is used to suggest opportunities, and staff decide who is referred. Entries you add are "
    "marked as self-reported until staff check them. You can only see your own record. Ask your "
    "officer to correct or remove anything you cannot change yourself."
)


class PortalError(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field, self.message = field, message


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---- staff: invite ---------------------------------------------------------------------------


def _account(participant):
    return YouthAccount.objects.select_related("user").filter(participant=participant).first()


def invite_status(participant) -> dict:
    account = _account(participant)
    if account is None:
        return {"state": "none"}
    if account.user.is_active:
        return {"state": "active", "consented_at": account.consented_at}
    last = account.invites.order_by("-created_at").first()
    return {
        "state": "pending",
        "invited_at": last.created_at if last else None,
        "expires_at": last.expires_at if last else None,
        "expired": bool(last and last.expires_at <= timezone.now()),
    }


@transaction.atomic
def send_invite(*, actor, participant, email):
    """Invite the youth to an address on their record. Replaces a pending invite."""
    if not access.has_permission(actor, "participants.view_contact"):
        raise PortalError("email", "You need access to contact details to send an invite.")
    wanted = (email or "").strip().lower()
    on_record = {e.strip().lower() for e in participants.email_addresses(participant)}
    if wanted not in on_record:
        raise PortalError("email", "Choose an e-mail address that is on this youth's record.")
    existing = _account(participant)
    if existing is not None:
        if existing.user.is_active:
            raise PortalError("email", "This youth already has an account.")
        identity.delete_pending_account(actor=actor, user=existing.user)  # replaces the invite
    try:
        user = identity.create_pending_account(actor=actor, email=wanted, role_name=ROLE)
    except identity.AccessError as exc:
        raise PortalError(exc.field, exc.message) from exc
    account = YouthAccount.objects.create(user=user, participant=participant)
    token = secrets.token_urlsafe(32)
    invite = YouthInvite.objects.create(
        account=account,
        email=wanted,
        token_hash=_hash(token),
        invited_by=actor,
        expires_at=timezone.now() + timedelta(days=INVITE_DAYS),
    )
    audit.record(
        actor=actor,
        action="youth.invited",
        object_type="participant",
        object_id=participant.pk,
        after={"expires_at": invite.expires_at.isoformat()},  # never the address or token
    )
    link = f"{settings.FRONTEND_URL.rstrip('/')}/youth/activate#token={token}"
    mail.send_mail(
        "Your CAP-YEI PI 360 invitation",
        f"Hello,\n\nYour CAP-YEI officer has invited you to see and update your own profile.\n"
        f"Use this link to choose a password. It works once and expires in {INVITE_DAYS} "
        f"days.\n\n{link}\n\nIf you were not expecting this, ignore this message.",
        None,
        [wanted],
    )
    return invite_status(participant)


@transaction.atomic
def withdraw_invite(*, actor, participant):
    account = _account(participant)
    if account is None or account.user.is_active:
        raise PortalError("invite", "There is no pending invite to withdraw.")
    identity.delete_pending_account(actor=actor, user=account.user)
    audit.record(
        actor=actor,
        action="youth.invite_withdrawn",
        object_type="participant",
        object_id=participant.pk,
    )


# ---- public: activate ------------------------------------------------------------------------


def _open_invite(token, *, lock=False):
    qs = YouthInvite.objects.select_related("account__user", "account__participant")
    if lock:
        qs = qs.select_for_update()
    invite = qs.filter(token_hash=_hash(token or "")).first()
    if (
        invite is None
        or invite.used_at is not None
        or invite.expires_at <= timezone.now()
        or invite.account.user.is_active
    ):
        raise PortalError("token", "This invitation link is invalid or has expired.")
    return invite


def check_invite(token) -> None:
    _open_invite(token)


@transaction.atomic
def activate(*, token, password):
    invite = _open_invite(token, lock=True)
    user = invite.account.user
    try:
        identity.activate_account(user=user, password=password)
    except identity.AccessError as exc:
        raise PortalError("password", exc.message) from exc
    invite.used_at = timezone.now()
    invite.save(update_fields=["used_at"])
    audit.record(
        actor=user,
        action="youth.invite_accepted",
        object_type="participant",
        object_id=invite.account.participant_id,
    )
    return user


# ---- the youth: own record -------------------------------------------------------------------


def _own(user):
    account = (
        YouthAccount.objects.select_related("participant")
        .filter(user=user, user__is_active=True)
        .first()
    )
    if account is None or not access.has_permission(user, SELF_SERVICE):
        raise PortalError("account", "No youth record is linked to this account.")
    return account


def _consented(account) -> bool:
    return account.consent_version == CONSENT_VERSION and account.consented_at is not None


def read(user) -> dict:
    account = _own(user)
    out = {
        "name": participants.display_name(account.participant),
        "consent": {
            "version": CONSENT_VERSION,
            "text": CONSENT_TEXT,
            "given": _consented(account),
            "given_at": account.consented_at,
        },
    }
    if out["consent"]["given"]:
        out["profile"] = {
            **participants.read_profile(account.participant, hide_staff=True),
            "options": participants.profile_options(),
        }
    return out


@transaction.atomic
def give_consent(*, user, version):
    account = _own(user)
    if version != CONSENT_VERSION:
        raise PortalError("version", "The notice has changed. Reload the page and read it again.")
    account.consent_version = version
    account.consented_at = timezone.now()
    account.save(update_fields=["consent_version", "consented_at"])
    audit.record(
        actor=user,
        action="youth.consent_given",
        object_type="participant",
        object_id=account.participant_id,
        after={"version": version},
    )
    return read(user)


def write_profile(*, user, data) -> dict:
    account = _own(user)
    if not _consented(account):
        raise PortalError("consent", "Accept the notice before editing your profile.")
    try:
        participants.write_profile(
            actor=user,
            p=account.participant,
            data=data,
            source="youth",
        )
    except participants.ProfileError as exc:
        raise PortalError(exc.field, str(exc)) from exc
    return read(user)
