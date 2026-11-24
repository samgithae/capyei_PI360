"""Disability (D-082, NEW-040, NEW-073).

Yes / No with an optional description when Yes; no "Prefer not to say" (D-082). A youth nobody has
asked stays ``not_recorded`` and nothing is inferred. It is deliberately a sub-resource of its own:
it is not in the participant detail, the list, exports or the CV, so it can only be reached here.

Three guards, all required: the flag ``participants.disability`` (off: the routes answer 404), the
permission ``participants.view_disability`` (in no default role), and the youth being in the
caller's scope. Every read and every change writes an access-log event. The event carries who,
which youth and what was done, never the answer or the description: an audit row that held the
value would spread it to everyone who may read the audit log.
"""

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit

from .models import Participant

FLAG = "participants.disability"
PERMISSION = "participants.view_disability"
VIEWED, CHANGED = "participant.disability_viewed", "participant.disability_changed"
SOURCES = ("staff", "self", "import")


class DisabilityError(ValueError):
    def __init__(self, message, field="disability"):
        super().__init__(message)
        self.field = field


def read(*, actor, p: Participant) -> dict:
    """The stored answer, logged as a read (the value is not in the log)."""
    audit.record(actor=actor, action=VIEWED, object_type="participant", object_id=p.pk, after=None)
    return _doc(p)


def _doc(p: Participant) -> dict:
    return {
        "disability": p.disability,
        "description": p.disability_description,
        "recorded_at": p.disability_recorded_at.isoformat() if p.disability_recorded_at else None,
        "source": p.disability_source,
    }


@transaction.atomic
def write(*, actor, p: Participant, answer: str, description: str = "", source="staff") -> dict:
    """Record yes / no. A description is kept only with Yes. Clearing back to "not recorded" is
    allowed (a mistake, or the youth withdrew the answer) and wipes the description."""
    if answer not in {v for v, _ in Participant.DISABILITY_VALUES}:
        raise DisabilityError("Choose Yes or No.")
    if source not in SOURCES:
        raise DisabilityError("Unknown source.", "source")
    description = (description or "").strip()
    if answer != Participant.DISABILITY_YES:
        description = ""
    if len(description) > 300:
        raise DisabilityError("Keep the description under 300 characters.", "description")
    changed = (p.disability, p.disability_description) != (answer, description)
    p.disability, p.disability_description = answer, description
    if answer == Participant.DISABILITY_NOT_RECORDED:
        p.disability_recorded_at, p.disability_source = None, ""
    elif changed or p.disability_recorded_at is None:
        p.disability_recorded_at, p.disability_source = timezone.now(), source
    Participant.objects.filter(pk=p.pk).update(
        disability=p.disability,
        disability_description=p.disability_description,
        disability_recorded_at=p.disability_recorded_at,
        disability_source=p.disability_source,
    )
    audit.record(
        actor=actor,
        action=CHANGED,
        object_type="participant",
        object_id=p.pk,
        after={"changed": changed},  # never the answer or the description
    )
    return _doc(p)
