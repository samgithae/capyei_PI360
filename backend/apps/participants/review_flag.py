"""The review flag (D-084, NEW-050): a work list of youth whose record someone should look at.

It is separate from ``Participant.status`` and blocks nothing: matching, referrals and the youth's
own portal ignore it. Four things set it (self-registration linked, the youth edited key details,
an import changed key fields, an officer flagged it with a reason). Any officer who can see the
youth and holds ``participants.edit`` may mark it reviewed, one at a time or in bulk."""

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit

from .models import Participant, ReviewEvent

SELF_REGISTRATION, SELF_EDIT, IMPORT_CHANGE, OFFICER = (
    "self_registration",
    "self_edit",
    "import_change",
    "officer_flag",
)
REASONS = {
    SELF_REGISTRATION: "Signed themselves up and was linked to this record",
    SELF_EDIT: "Changed their own details",
    IMPORT_CHANGE: "An import changed key fields",
    OFFICER: "Flagged by an officer",
}
SELF_EDIT_KEYS = {"given_name", "family_name", "other_names", "gender", "date_of_birth",
                  "full_name_source", "origin_county_id"}  # fmt: skip


class ReviewError(ValueError):
    def __init__(self, message, field="review"):
        super().__init__(message)
        self.field = field


def flag(*, p: Participant, reason: str, actor=None, note: str = "") -> None:
    """Put the youth on the work list. Flagging again keeps one open flag but records each cause
    in the history, and the latest cause is the one shown."""
    if reason not in REASONS:
        raise ReviewError("Unknown reason.", "reason")
    note = (note or "").strip()[:500]
    since = p.review_since if p.review_state == Participant.REVIEW_NEEDED else timezone.now()
    p.review_state, p.review_reason, p.review_since = Participant.REVIEW_NEEDED, reason, since
    Participant.objects.filter(pk=p.pk).update(
        review_state=p.review_state, review_reason=reason, review_since=since
    )
    ReviewEvent.objects.create(
        participant=p, kind=ReviewEvent.FLAGGED, reason=reason, note=note,
        actor=actor if getattr(actor, "pk", None) else None,
    )  # fmt: skip
    audit.record(
        actor=actor if getattr(actor, "pk", None) else None,
        action="participant.review_flagged",
        object_type="participant",
        object_id=p.pk,
        after={"reason": reason},  # never the note: it is free text
    )


def officer_flag(*, actor, p: Participant, note: str) -> None:
    if not (note or "").strip():
        raise ReviewError("Say why this record needs a look.", "note")
    flag(p=p, reason=OFFICER, actor=actor, note=note)


@transaction.atomic
def mark_reviewed(*, actor, participants, note: str = "") -> int:
    """Clear the flag for the given youth (already limited to what the actor may see). Returns
    how many were actually open; those not on the list are left alone."""
    n = 0
    for p in participants:
        if p.review_state != Participant.REVIEW_NEEDED:
            continue
        Participant.objects.filter(pk=p.pk).update(
            review_state=Participant.REVIEW_DONE, review_since=None
        )
        ReviewEvent.objects.create(
            participant=p, kind=ReviewEvent.REVIEWED, reason=p.review_reason,
            note=(note or "").strip()[:500], actor=actor,
        )  # fmt: skip
        audit.record(
            actor=actor, action="participant.review_done", object_type="participant",
            object_id=p.pk, before={"state": Participant.REVIEW_NEEDED},
            after={"state": Participant.REVIEW_DONE},
        )  # fmt: skip
        n += 1
    return n


def history(p: Participant) -> list[dict]:
    return [
        {
            "kind": e.kind,
            "reason": e.reason,
            "reason_label": REASONS.get(e.reason, ""),
            "note": e.note,
            "by": e.actor.get_username() if e.actor_id else "",
            "at": e.created_at.isoformat(),
        }
        for e in p.reviews.select_related("actor")
    ]
