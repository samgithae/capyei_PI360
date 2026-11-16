"""Employer portal (Phase 3): people who work for an employer sign in to that employer's records.

PI staff set up the first account (the company admin); that person invites colleagues and picks
their role. There is no open registration. A user belongs to one employer and every request is
resolved from that membership, never from an id the caller sends, so one company can never reach
another's records. Roles are ordinary roles made only of ``employer.*`` permissions; this module
offers a company admin those roles and no others.

This module coordinates identity (accounts, roles), employers (the company) and configuration
(two switches); none of them knows about the others.
"""

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core import mail
from django.db import transaction
from django.utils import timezone

from apps.api import access
from apps.audit import services as audit
from apps.configuration import services as configuration
from apps.employers import services as employers
from apps.identity import services as identity
from apps.referrals import services as referrals

from .models import EmployerInvite, EmployerMember

PORTAL = "employer.portal"
MANAGE_STAFF = "employer.manage_staff"
ROLE_PREFIX = "employer."
ADMIN_ROLE = "Company admin"
INVITE_DAYS = 7
MFA_FLAG = "employer_mfa_required"
SELF_PUBLISH_FLAG = "employer_self_publish"


class PortalError(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field, self.message = field, message


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---- who is this user, and which company --------------------------------------------------


def mfa_required(user) -> bool:
    """Second factor for an employer account: the ``employer_mfa_required`` switch, off unless an
    administrator turns it on. The switch can name roles (for example Company admin only)."""
    if not EmployerMember.objects.filter(user=user).exists():
        return False
    return configuration.is_enabled(MFA_FLAG, user)


def own_member(user) -> EmployerMember:
    """The signed-in user's membership. The one place every employer view finds "my company".
    Refused when the account is switched off or the company is no longer active."""
    member = (
        EmployerMember.objects.select_related("user")
        .filter(user=user, user__is_active=True)
        .first()
    )
    if member is None or not access.has_permission(user, PORTAL):
        raise PortalError("account", "No employer is linked to this account.")
    if not employers.is_active(member.employer_id):
        raise PortalError("account", "This company's access is switched off.")
    return member


def publishes_directly(user) -> bool:
    """May this person open an opportunity without PI staff approving it first? The
    ``employer_self_publish`` switch, off unless an administrator turns it on."""
    return configuration.is_enabled(SELF_PUBLISH_FLAG, user)


def own_employer_id(user):
    """Convenience for later phases: the company every query must be limited to."""
    return own_member(user).employer_id


def people(employer_id) -> dict:
    """``{user id: name}`` of everyone at the company, so a referral's history can tell the
    company's own moves from PI staff's."""
    return {m.user_id: m.full_name for m in EmployerMember.objects.filter(employer_id=employer_id)}


def me(user) -> dict:
    member = own_member(user)
    name = employers.brief_employers([member.employer_id]).get(member.employer_id, {})
    return {
        "employer": {"id": str(member.employer_id), "name": name.get("name", "")},
        "member": {
            "id": str(member.pk),
            "name": member.full_name,
            "job_title": member.job_title,
            "is_owner": member.is_owner,
        },
        "roles": identity.role_names(user),
    }


# ---- roles a company may hand out ----------------------------------------------------------


def assignable_roles() -> list[dict]:
    """Roles made only of employer permissions: the family a company admin chooses from."""
    return [r for r in identity.roles_limited_to(ROLE_PREFIX) if PORTAL in r["permissions"]]


def _role(role_id) -> dict:
    for r in assignable_roles():
        if r["id"] == role_id:
            return r
    raise PortalError("role", "Choose one of the employer roles.")


# ---- the team ------------------------------------------------------------------------------


def _state(member, last_invite):
    if member.user.is_active:
        return "active"
    if member.user.has_usable_password():
        return "suspended"
    if last_invite and last_invite.expires_at <= timezone.now():
        return "expired"
    return "pending"


def _row(member) -> dict:
    last = member.invites.order_by("-created_at").first()
    return {
        "id": str(member.pk),
        "contact_id": str(member.contact_id) if member.contact_id else None,
        "name": member.full_name,
        "email": member.user.email,
        "job_title": member.job_title,
        "is_owner": member.is_owner,
        "state": _state(member, last),
        "roles": identity.role_names(member.user),
        "invited_at": last.created_at if last else None,
        "expires_at": last.expires_at if last else None,
        "last_login": member.user.last_login,
    }


def team(employer_id) -> list[dict]:
    qs = EmployerMember.objects.filter(employer_id=employer_id).select_related("user")
    return [_row(m) for m in qs]


def people_list(employer_id) -> list[dict]:
    """One row per person on the company's contact list: their details, and ``access`` (the
    same row ``team`` returns) when they can sign in, else null."""
    members = {
        m.contact_id: m
        for m in EmployerMember.objects.filter(
            employer_id=employer_id, contact__isnull=False
        ).select_related("user")
    }
    return [
        {**c, "access": _row(members[uid]) if (uid := uuid.UUID(c["id"])) in members else None}
        for c in employers.contacts_of(employer_id)
    ]


def _member_of(employer_id, member_id) -> EmployerMember:
    member = (
        EmployerMember.objects.select_related("user")
        .filter(employer_id=employer_id, pk=member_id)
        .first()
    )
    if member is None:
        raise PortalError("account", "There is no such user at this company.")
    return member


def _active_admins(employer_id) -> list[EmployerMember]:
    return [
        m
        for m in EmployerMember.objects.filter(
            employer_id=employer_id, user__is_active=True
        ).select_related("user")
        if ADMIN_ROLE in identity.role_names(m.user)
    ]


def _guard_last_admin(member, what):
    admins = _active_admins(member.employer_id)
    if member.user.is_active and [a.pk for a in admins] == [member.pk]:
        raise PortalError("user", f"This is the company's only active admin: {what}.")


def _person_for_invite(*, actor, employer_id, contact_id, email, name, title, phone, is_primary):
    """The contact record the new account will belong to, created or brought up to date.

    Refused if that person already has an account (an address change would otherwise lock them
    out): the one sign-in they have stays theirs."""
    try:
        if contact_id:
            person = employers.own_contact(employer_id, contact_id)
        else:
            person = employers.contact_by_email(employer_id, email)
    except employers.Missing:
        raise PortalError("contact", "There is no such person at this company.") from None
    if person is not None:
        if EmployerMember.objects.filter(contact_id=person["id"]).exists():
            raise PortalError("contact", "This person already has an account at this company.")
        data = {"name": name, "email": email}
        if title:
            data["role"] = title
        return employers.save_own_contact(
            actor=actor, employer_id=employer_id, data=data, contact_id=person["id"]
        )
    return employers.save_own_contact(
        actor=actor,
        employer_id=employer_id,
        data={
            "name": name,
            "role": title,
            "email": email,
            "phone": (phone or "").strip(),
            "is_primary": bool(is_primary),
        },
    )


@transaction.atomic
def invite(
    *,
    actor,
    employer_id,
    email,
    full_name,
    role_id,
    job_title="",
    first=False,
    contact_id=None,
    phone="",
    is_primary=False,
):
    """Invite a person to the company. Replaces a pending invite for the same address.

    The person is one record on the company's contact list: ``contact_id`` gives portal access to a
    person already listed; otherwise a listed contact with the same e-mail address is used, or a
    new one is made. ``phone`` and ``is_primary`` apply only to a contact made here.

    Staff (``employers.invite_user``) and a company admin (``employer.manage_staff``) both call
    this; the view has checked the permission and, for a company admin, that ``employer_id`` is
    their own. ``first`` marks the account PI staff set up for the company."""
    if not employers.exists(employer_id):
        raise PortalError("employer", "There is no such employer.")
    if not employers.is_active(employer_id):
        raise PortalError("employer", "This employer is inactive or archived.")
    wanted = (email or "").strip().lower()
    name = (full_name or "").strip()
    if not name:
        raise PortalError("full_name", "Enter the person's name.")
    role = _role(role_id)
    existing = (
        EmployerMember.objects.select_related("user")
        .filter(employer_id=employer_id, user__email__iexact=wanted)
        .first()
    )
    if existing is not None:
        if existing.user.is_active or existing.user.has_usable_password():
            raise PortalError("email", "This person already has an account at this company.")
        identity.delete_pending_account(actor=actor, user=existing.user)  # replaces the invite
    title = (job_title or "").strip()
    person = _person_for_invite(
        actor=actor,
        employer_id=employer_id,
        contact_id=contact_id,
        email=wanted,
        name=name,
        title=title,
        phone=phone,
        is_primary=is_primary,
    )
    try:
        user = identity.create_pending_account(actor=actor, email=wanted, role_name=role["name"])
    except identity.AccessError as exc:
        raise PortalError(exc.field, exc.message) from exc
    member = EmployerMember.objects.create(
        user=user,
        employer_id=employer_id,
        contact_id=person["id"],
        full_name=name,
        job_title=title or person["role"],
        is_owner=first,
        created_by=actor,
    )
    token = secrets.token_urlsafe(32)
    link_row = EmployerInvite.objects.create(
        member=member,
        email=wanted,
        token_hash=_hash(token),
        invited_by=actor,
        expires_at=timezone.now() + timedelta(days=INVITE_DAYS),
    )
    audit.record(
        actor=actor,
        action="employer_user.invited",
        object_type="employer",
        object_id=employer_id,
        after={
            "member": str(member.pk),
            "role": role["name"],
            "expires_at": link_row.expires_at.isoformat(),
        },
    )  # never the address or the token
    company = employers.brief_employers([employer_id]).get(employer_id, {}).get("name", "")
    link = f"{settings.FRONTEND_URL.rstrip('/')}/employer/activate#token={token}"
    mail.send_mail(
        "Your CAP-YEI PI 360 invitation",
        f"Hello {name},\n\nYou have been invited to manage {company}'s opportunities and referrals "
        f"on CAP-YEI Placement Intelligence 360.\nUse this link to choose a password. It works "
        f"once and expires in {INVITE_DAYS} days.\n\n{link}\n\nIf you were not expecting this, "
        f"ignore this message.",
        None,
        [wanted],
    )
    return _row(member)


@transaction.atomic
def withdraw_invite(*, actor, employer_id, member_id):
    member = _member_of(employer_id, member_id)
    if member.user.is_active or member.user.has_usable_password():
        raise PortalError("invite", "There is no pending invite to withdraw.")
    identity.delete_pending_account(actor=actor, user=member.user)
    audit.record(
        actor=actor,
        action="employer_user.invite_withdrawn",
        object_type="employer",
        object_id=employer_id,
        after={"member": str(member_id)},
    )


@transaction.atomic
def change_role(*, actor, employer_id, member_id, role_id):
    member = _member_of(employer_id, member_id)
    role = _role(role_id)
    current = identity.role_names(member.user)
    if ADMIN_ROLE in current and role["name"] != ADMIN_ROLE:
        _guard_last_admin(member, "make another person admin first")
    family = {r["name"] for r in assignable_roles()}
    for name in current:
        if name in family and name != role["name"]:
            identity.remove_role(actor=actor, user=member.user, role=_role_by_name(name))
    identity.assign_role(actor=actor, user=member.user, role=identity.get_role(role["id"]))
    return _row(member)


def _role_by_name(name):
    for r in assignable_roles():
        if r["name"] == name:
            return identity.get_role(r["id"])
    raise PortalError("role", "Choose one of the employer roles.")


@transaction.atomic
def set_active(*, actor, employer_id, member_id, active, reason=""):
    """Suspend or reactivate a person. A suspended person is signed out at once."""
    member = _member_of(employer_id, member_id)
    if not member.user.has_usable_password():
        raise PortalError("user", "This person has not accepted the invitation yet.")
    try:
        if active:
            identity.reactivate_user(actor=actor, user=member.user, reason=reason)
        else:
            if actor is not None and actor.pk == member.user_id:
                raise PortalError("user", "You cannot suspend your own account.")
            _guard_last_admin(member, "make another person admin first")
            identity.suspend_user(actor=actor, user=member.user, reason=reason)
    except identity.AccessError as exc:
        raise PortalError(exc.field, exc.message) from exc
    member.user.refresh_from_db()
    return _row(member)


# ---- public: activate ------------------------------------------------------------------------


def _open_invite(token, *, lock=False):
    qs = EmployerInvite.objects.select_related("member__user")
    if lock:
        qs = qs.select_for_update(of=("self",))
    invite_row = qs.filter(token_hash=_hash(token or "")).first()
    if (
        invite_row is None
        or invite_row.used_at is not None
        or invite_row.expires_at <= timezone.now()
        or invite_row.member.user.is_active
        or not employers.is_active(invite_row.member.employer_id)
    ):
        raise PortalError("token", "This invitation link is invalid or has expired.")
    return invite_row


def check_invite(token) -> None:
    _open_invite(token)


@transaction.atomic
def activate(*, token, password):
    invite_row = _open_invite(token, lock=True)
    user = invite_row.member.user
    try:
        identity.activate_account(user=user, password=password)
    except identity.AccessError as exc:
        raise PortalError("password", exc.message) from exc
    invite_row.used_at = timezone.now()
    invite_row.save(update_fields=["used_at"])
    audit.record(
        actor=user,
        action="employer_user.invite_accepted",
        object_type="employer",
        object_id=invite_row.member.employer_id,
        after={"member": str(invite_row.member.pk)},
    )
    return user


# ---- dashboard -----------------------------------------------------------------------------


def dashboard(user) -> dict:
    """What matters to this person today. Each section is included only when the person's role may
    open the list behind it, and every figure carries the list it counts (``link``)."""
    member = own_member(user)
    eid = member.employer_id
    can = {
        "opportunities": access.has_permission(user, "employer.view_opportunities"),
        "referrals": access.has_permission(user, "employer.view_referrals"),
        "team": access.has_permission(user, MANAGE_STAFF),
    }
    today = timezone.localdate()
    out: dict = {"can": can, "attention": [], "activity": []}
    if can["opportunities"]:
        opp = employers.opportunity_figures(eid, today)
        out["opportunities"] = opp
        if opp["closing_soon"]:
            soon = employers.own_opportunities(eid, view="closing_soon", size=5, today=today)
            for o in soon["results"]:
                out["activity"].append(
                    {
                        "kind": "closing",
                        "at": o["closing_date"],
                        "text": f"{o['title']} closes on {o['closing_date']}",
                        "link": f"/employer/opportunities/{o['id']}",
                    }
                )
            out["attention"].append(
                {
                    "kind": "closing",
                    "count": opp["closing_soon"],
                    "text": f"{opp['closing_soon']} opportunit"
                    f"{'y closes' if opp['closing_soon'] == 1 else 'ies close'} within a week",
                    "link": "/employer/opportunities?view=closing_soon",
                }
            )
        if opp["expired"]:
            out["attention"].append(
                {
                    "kind": "expired",
                    "count": opp["expired"],
                    "text": f"{opp['expired']} opportunit"
                    f"{'y has' if opp['expired'] == 1 else 'ies have'} passed the closing date",
                    "link": "/employer/opportunities?view=expired",
                }
            )
        if opp["declined"]:
            out["attention"].append(
                {
                    "kind": "declined",
                    "count": opp["declined"],
                    "text": f"{opp['declined']} publish request"
                    f"{' was' if opp['declined'] == 1 else 's were'} sent back with a reason",
                    "link": "/employer/opportunities?view=declined",
                }
            )
    if can["referrals"]:
        data = referrals.own_dashboard(eid, people=people(eid))
        out["referrals"] = data
        waiting = data["figures"]["waiting"]
        if waiting:
            out["attention"].insert(
                0,
                {
                    "kind": "waiting",
                    "count": waiting,
                    "text": f"{waiting} new referral{'' if waiting == 1 else 's'} waiting more "
                    f"than {data['waiting_days']} days for your reply",
                    "link": "/employer/referrals?view=waiting",
                },
            )
        for a in data["new_arrivals"]:
            out["activity"].append(
                {
                    "kind": "new_referrals",
                    "at": a["at"],
                    "text": f"{a['count']} new referral{'' if a['count'] == 1 else 's'} for "
                    f"{a['opportunity']}",
                    "link": f"/employer/referrals?opportunity={a['opportunity_id']}",
                }
            )
        for m in data["recent_moves"]:
            who = "you" if m["by"] == member.full_name else m["by"]
            out["activity"].append(
                {
                    "kind": "move",
                    "at": m["at"],
                    "text": f"{m['candidate']} moved to {m['label'].lower()} by {who}",
                    "link": f"/employer/referrals/{m['referral_id']}",
                }
            )
    if can["team"]:
        pending = [m for m in team(eid) if m["state"] in ("pending", "expired")]
        for m in pending:
            out["activity"].append(
                {
                    "kind": "invite",
                    "at": m["invited_at"].isoformat() if m["invited_at"] else None,
                    "text": f"Invite for {m['name']} not yet accepted"
                    + (" (expired)" if m["state"] == "expired" else ""),
                    "link": "/employer/people",
                }
            )
        if pending:
            out["attention"].append(
                {
                    "kind": "invites",
                    "count": len(pending),
                    "text": f"{len(pending)} invitation{'' if len(pending) == 1 else 's'} not yet "
                    "accepted",
                    "link": "/employer/people",
                }
            )
    out["activity"] = sorted(out["activity"], key=lambda a: a["at"] or "", reverse=True)[:15]
    return out
