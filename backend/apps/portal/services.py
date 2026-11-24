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
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.api import access
from apps.audit import services as audit
from apps.identity import services as identity
from apps.participants import services as participants
from apps.placements import services as placements
from apps.referrals import services as referrals

from .models import RegistrationRequest, YouthAccount, YouthInvite

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


def has_account(participant_id) -> bool:
    """True if this youth record already has a portal account (NEW-077 merge check)."""
    return YouthAccount.objects.filter(participant_id=participant_id).exists()


def invite_status(participant) -> dict:
    account = _account(participant)
    if account is None:
        return {"state": "none"}
    if account.user.is_active:
        return {
            "state": "active",
            "consented_at": account.consented_at,
            "created_at": account.created_at,
            "last_login": account.user.last_login,
        }
    last = account.invites.order_by("-created_at").first()
    return {
        "state": "pending",
        "invited_at": last.created_at if last else None,
        "expires_at": last.expires_at if last else None,
        "expired": bool(last and last.expires_at <= timezone.now()),
    }


@transaction.atomic
def send_invite(*, actor, participant, email, verified_address=False):
    """Invite the youth to an address on their record. Replaces a pending invite.

    ``verified_address`` is only for a sign-up the youth confirmed themselves (NEW-047): the
    address came from them, so it need not be on the record and the officer needs no access to
    contact details."""
    wanted = (email or "").strip().lower()
    if not verified_address:
        if not access.has_permission(actor, "participants.view_contact"):
            raise PortalError("email", "You need access to contact details to send an invite.")
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
        out["details"] = participants.read_own_details(account.participant)
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


def _consented_participant(user, what):
    account = _own(user)
    if not _consented(account):
        raise PortalError("consent", f"Accept the notice before {what}.")
    return account.participant


def cv(*, user) -> dict:
    """The youth's own CV, from what is saved now."""
    return participants.build_cv(_consented_participant(user, "viewing your CV"))


def cv_pdf(*, user) -> tuple[bytes, str]:
    return participants.cv_pdf(actor=user, p=_consented_participant(user, "downloading your CV"))


def photo(*, user):
    return participants.get_photo(_consented_participant(user, "viewing your photo"))


def set_photo(*, user, raw: bytes) -> None:
    p = _consented_participant(user, "adding a photo")
    try:
        participants.save_photo(actor=user, p=p, raw=raw)
    except participants.PhotoError as exc:
        raise PortalError(exc.field, str(exc)) from exc


def clear_photo(*, user) -> None:
    participants.remove_photo(actor=user, p=_consented_participant(user, "changing your photo"))


def write_details(*, user, data) -> dict:
    account = _own(user)
    if not _consented(account):
        raise PortalError("consent", "Accept the notice before editing your details.")
    try:
        participants.write_own_details(actor=user, p=account.participant, data=data)
    except participants.DetailsError as exc:
        raise PortalError(exc.field, str(exc)) from exc
    return read(user)


def journey(*, user) -> dict:
    """The learner's dashboard: counters, journey steps and their own referrals."""
    account = _own(user)
    if not _consented(account):
        raise PortalError("consent", "Accept the notice before using your dashboard.")
    return referrals.learner_journey(account.participant_id)


def opportunity(*, user, referral_id) -> dict:
    account = _own(user)
    if not _consented(account):
        raise PortalError("consent", "Accept the notice before using your dashboard.")
    row = referrals.learner_referral(account.participant_id, referral_id)
    if row is None:
        raise PortalError("account", "Not found.")
    return row


def _consented_account(user):
    account = _own(user)
    if not _consented(account):
        raise PortalError("consent", "Accept the notice before using your dashboard.")
    return account


def notices(*, user) -> dict:
    account = _consented_account(user)
    return referrals.learner_notices(account.participant_id, account.notices_seen_at)


def mark_notices_seen(*, user) -> dict:
    account = _consented_account(user)
    account.notices_seen_at = timezone.now()
    account.save(update_fields=["notices_seen_at"])
    return referrals.learner_notices(account.participant_id, account.notices_seen_at)


def placement(*, user) -> dict:
    """The learner's own placements: imported records and placed referrals."""
    account = _consented_account(user)
    pid = account.participant_id
    return {
        "placements": placements.for_enrollments(participants.enrollment_ids(pid)),
        "referrals": referrals.learner_placed(pid),
    }


# --- self-registration requests (NEW-044, NEW-072; D-083) ---------------------------------
# Switched off by the flag `portal.self_registration`. The public sign-up endpoints (NEW-045) and
# approve/link (NEW-046) build on this; for now stewards can see the queue and reject or delete.

REGISTRATION_FLAG = "portal.self_registration"
OTP_MAX_ATTEMPTS = 5


class RegistrationFailure(Exception):
    def __init__(self, message, field="non_field_errors"):
        super().__init__(message)
        self.message, self.field = message, field


def _normal_phone(value: str) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    return ("+" if (value or "").strip().startswith("+") else "") + digits


def start_registration(
    *, given_name, family_name, date_of_birth, gender="", email="", phone="",
    programme_code="", enrollment_no="", consent_version="", ip="",
):  # fmt: skip
    """Record a sign-up. Returns the request and the raw token and code to send; only their
    hashes are stored, and the caller must not log them."""
    email, phone = (email or "").strip().lower(), _normal_phone(phone)
    if not (email or phone):
        raise RegistrationFailure("Give an e-mail address or a phone number.", "email")
    token, otp = secrets.token_urlsafe(32), f"{secrets.randbelow(10**6):06d}"
    req = RegistrationRequest.objects.create(
        given_name=given_name.strip(), family_name=family_name.strip(),
        date_of_birth=date_of_birth, gender=gender, email=email, phone=phone,
        claimed_programme_code=programme_code.strip(), claimed_enrollment_no=enrollment_no.strip(),
        verify_token_hash=_hash(token) if email else "",
        otp_hash=_hash(f"{phone}:{otp}") if phone else "",
        verify_expires_at=timezone.now() + timedelta(days=INVITE_DAYS),
        consent_version=consent_version,
        ip_hash=_hash(f"{settings.SECRET_KEY}:{ip}") if ip else "",
    )  # fmt: skip
    return req, token, otp


def registration_queue(*, status="", search=""):
    qs = RegistrationRequest.objects.all()
    if status:
        qs = qs.filter(status=status)
    if search.strip():
        s = search.strip()
        qs = qs.filter(
            Q(given_name__icontains=s) | Q(family_name__icontains=s)
            | Q(email__icontains=s) | Q(phone__icontains=s)
        )  # fmt: skip
    return qs


def registration_counts() -> dict:
    rows = RegistrationRequest.objects.values("status").annotate(n=Count("pk"))
    return {r["status"]: r["n"] for r in rows}


def _open(req):
    if req.status in (RegistrationRequest.APPROVED, RegistrationRequest.LINKED):
        raise RegistrationFailure("This request has already been settled.")
    return req


@transaction.atomic
def reject_registration(*, actor, req, reason):
    if not (reason or "").strip():
        raise RegistrationFailure("Say why you are rejecting this request.", "reason")
    _open(req)
    before = req.status
    req.status = RegistrationRequest.REJECTED
    req.reviewed_by, req.reviewed_at = actor, timezone.now()
    req.decision_reason = reason.strip()
    req.save(update_fields=["status", "reviewed_by", "reviewed_at", "decision_reason"])
    audit.record(
        actor=actor, action="registration.rejected", object_type="registration",
        object_id=req.pk, before={"status": before}, after={"status": req.status}, reason=reason,
    )  # fmt: skip
    return req


@transaction.atomic
def delete_registration(*, actor, req):
    """Rejected and expired requests stay until an administrator deletes them (D-083)."""
    if req.status not in (RegistrationRequest.REJECTED, RegistrationRequest.EXPIRED):
        raise RegistrationFailure("Only rejected or expired requests can be deleted.")
    pk = req.pk
    req.delete()
    audit.record(
        actor=actor, action="registration.deleted", object_type="registration", object_id=pk,
        before={"status": req.status}, after=None, reason="",
    )  # fmt: skip


# --- public sign-up (NEW-045) -----------------------------------------------------------------
# Every answer to the public looks the same whether or not the person, e-mail or number is already
# known, so the form cannot be used to find out who is in the system. SMS is not connected, so for
# now a sign-up is verified by e-mail only (phone verification arrives with an SMS channel).

REGISTER_PER_CONTACT = 3  # sign-ups per e-mail address per hour; extras are dropped quietly
OPEN_STATES = (RegistrationRequest.PENDING,)


def _contact_allowed(email: str) -> bool:
    key = f"register:{_hash(email)}"
    cache.add(key, 0, timeout=3600)
    try:
        return cache.incr(key) <= REGISTER_PER_CONTACT
    except ValueError:  # key expired between add and incr
        return True


def _send_verification(email: str, token: str):
    link = f"{settings.FRONTEND_URL.rstrip('/')}/register/verify#token={token}"
    mail.send_mail(
        "Confirm your CAP-YEI PI 360 registration",
        f"Hello,\n\nUse this link to confirm your e-mail address. It works once and expires in "
        f"{INVITE_DAYS} days.\n\n{link}\n\nIf you did not sign up, ignore this message.",
        None,
        [email],
    )


def submit_registration(
    *, given_name, family_name, date_of_birth, email, gender="", phone="",
    programme_code="", enrollment_no="", ip="",
):  # fmt: skip
    """Take a sign-up. Returns nothing whatever happened, so the reply is always the same."""
    email = (email or "").strip().lower()
    if not _contact_allowed(email):
        return
    existing = RegistrationRequest.objects.filter(email=email).first()
    if existing is not None:
        if existing.status in OPEN_STATES:  # they lost the mail: send a fresh link, same request
            token = secrets.token_urlsafe(32)
            existing.verify_token_hash = _hash(token)
            existing.verify_expires_at = timezone.now() + timedelta(days=INVITE_DAYS)
            existing.save(update_fields=["verify_token_hash", "verify_expires_at"])
            _send_verification(email, token)
        return  # already known: say nothing, send nothing
    req, token, _otp = start_registration(
        given_name=given_name, family_name=family_name, date_of_birth=date_of_birth,
        gender=gender, email=email, phone="", programme_code=programme_code,
        enrollment_no=enrollment_no, consent_version=CONSENT_VERSION, ip=ip,
    )  # fmt: skip
    if phone:  # kept for the steward; not verified until SMS exists
        req.phone = _normal_phone(phone)
        req.save(update_fields=["phone"])
    audit.record(
        actor=None, action="registration.submitted", object_type="registration",
        object_id=req.pk, after={"status": req.status},
    )  # fmt: skip
    _send_verification(email, token)


def verify_registration(token: str):
    """Confirm the e-mail. One generic failure for a wrong, used or expired link."""
    req = RegistrationRequest.objects.filter(
        verify_token_hash=_hash(token or ""), status=RegistrationRequest.PENDING
    ).first()
    if req is None or not req.verify_token_hash or req.verify_expires_at < timezone.now():
        raise RegistrationFailure("This link is not valid or has expired.", "token")
    req.email_verified_at = timezone.now()
    req.status = RegistrationRequest.VERIFIED
    req.verify_token_hash = ""  # single use
    req.save(update_fields=["email_verified_at", "status", "verify_token_hash"])
    audit.record(
        actor=None, action="registration.verified", object_type="registration",
        object_id=req.pk, after={"status": req.status},
    )  # fmt: skip


# --- officer review: link or create (NEW-046) -----------------------------------------------

REVIEWABLE = (RegistrationRequest.VERIFIED, RegistrationRequest.REVIEW)


def _reviewable(req):
    if req.status not in REVIEWABLE:
        raise RegistrationFailure(
            "Only a verified request can be reviewed. Wait until the youth confirms their e-mail."
        )


def registration_matches(*, actor, req) -> list[dict]:
    """People the officer may see who look like this sign-up. Also remembers whether any exist
    (``possible_duplicate``), so the queue can show it."""
    found = participants.similar_visible(
        actor,
        name=f"{req.given_name} {req.family_name}",
        phone=req.phone,
        birth_date=req.date_of_birth,
    )
    flag = bool(found)
    if flag != req.possible_duplicate and req.status in REVIEWABLE:
        req.possible_duplicate = flag
        req.save(update_fields=["possible_duplicate"])
    return found


@transaction.atomic
def link_registration(*, actor, req, participant_id, reason):
    """Attach the sign-up to a record that already exists. Never creates a person."""
    _reviewable(req)
    if not (reason or "").strip():
        raise RegistrationFailure("Say why you are linking this request.", "reason")
    if not participants.is_visible(actor, participant_id):
        raise RegistrationFailure("That youth record was not found.", "participant_id")
    if (
        RegistrationRequest.objects.filter(
            participant_id=participant_id,
            status__in=[RegistrationRequest.LINKED, RegistrationRequest.APPROVED],
        )
        .exclude(pk=req.pk)
        .exists()
    ):
        raise RegistrationFailure(
            "Another sign-up is already linked to that record.", "participant_id"
        )
    before = req.status
    req.status, req.participant_id = RegistrationRequest.LINKED, participant_id
    req.reviewed_by, req.reviewed_at, req.decision_reason = actor, timezone.now(), reason.strip()
    req.save(
        update_fields=["status", "participant", "reviewed_by", "reviewed_at", "decision_reason"]
    )
    audit.record(
        actor=actor, action="registration.linked", object_type="registration", object_id=req.pk,
        before={"status": before}, after={"status": req.status, "participant": str(participant_id)},
        reason=reason,
    )  # fmt: skip
    # The sign-up details were typed by the youth, not checked: put the record on the work list.
    linked = participants.find_active(participant_id)
    if linked is not None:
        participants.flag_for_review(p=linked, reason="self_registration", actor=actor)
    return req


@transaction.atomic
def create_registration(*, actor, req, reason, confirm_similar=False):
    """Make a new youth record from the sign-up. When someone similar is already on file the
    officer must say they have looked (``confirm_similar``); otherwise it is refused."""
    _reviewable(req)
    if not (reason or "").strip():
        raise RegistrationFailure("Say why you are creating a new record.", "reason")
    similar = registration_matches(actor=actor, req=req)
    if similar and not confirm_similar:
        raise RegistrationFailure(
            "Someone similar is already on file. Link to them, or confirm this is a new person.",
            "confirm_similar",
        )
    p = participants.create_from_signup(
        actor=actor,
        req_data={
            "given_name": req.given_name, "family_name": req.family_name, "gender": req.gender,
            "date_of_birth": req.date_of_birth, "email": req.email, "phone": req.phone,
        },
    )  # fmt: skip
    before = req.status
    req.status, req.participant = RegistrationRequest.APPROVED, None
    req.participant_id = p.pk
    req.reviewed_by, req.reviewed_at, req.decision_reason = actor, timezone.now(), reason.strip()
    req.save(
        update_fields=["status", "participant", "reviewed_by", "reviewed_at", "decision_reason"]
    )
    audit.record(
        actor=actor, action="registration.created_new", object_type="registration",
        object_id=req.pk, before={"status": before},
        after={"status": req.status, "participant": str(p.pk), "similar_confirmed": bool(similar)},
        reason=reason,
    )  # fmt: skip
    return req


def invite_registrant(*, actor, req) -> dict:
    """After an officer approves or links a sign-up, send the normal youth invite to the address
    the youth confirmed (NEW-047). It is the same invite and activation as for staff-sent ones, so
    there is still one account per youth record. The decision stands even if the invite cannot be
    sent; the officer can then use the invite card on the youth's page."""
    if req.status not in (RegistrationRequest.APPROVED, RegistrationRequest.LINKED):
        return {"sent": False, "reason": "not_decided"}
    if req.email_verified_at is None:
        return {"sent": False, "reason": "unverified_email"}
    participant = participants.find_active(req.participant_id)
    if participant is None:
        return {"sent": False, "reason": "record_unavailable"}
    account = _account(participant)
    if account is not None and account.user.is_active:
        return {"sent": False, "reason": "already_has_account"}
    try:
        send_invite(actor=actor, participant=participant, email=req.email, verified_address=True)
    except PortalError as exc:
        return {"sent": False, "reason": "refused", "message": exc.message}
    except Exception:  # noqa: BLE001 - mail down: keep the decision, tell the officer
        return {"sent": False, "reason": "mail_failed"}
    return {"sent": True, "reason": ""}
