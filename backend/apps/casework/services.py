"""Case management (T-064 work queue, T-065 placements and episodes).

A coordination module, like the youth portal: it has no tables of its own. It puts the record
scope (which youth the caller may see) in front of the placement history, and gathers the
officer's work queue from interventions, referrals, flags and placements, each of which stays
inside its own module."""

from datetime import date

from django.utils import timezone

from apps.api.access import has_permission
from apps.audit import services as audit
from apps.employers import services as employers
from apps.intelligence import services as intelligence
from apps.participants import services as participants
from apps.placements import services as placements
from apps.referrals import services as referrals

PATHWAY_NAMES = dict(placements.Placement.PATHWAYS)
SOURCE_NAMES = dict(placements.Placement.SOURCES)
FLAG_LIMIT = 10


class NotFound(Exception):
    pass


class Violation(Exception):
    """A rule the request broke; shown next to the field."""

    def __init__(self, field, message, code="invalid"):
        super().__init__(message)
        self.field, self.message, self.code = field, message, code


# --- placements ------------------------------------------------------------------------------


def _owners(user) -> dict:
    """``{enrollment id: participant id}`` for youth inside the user's scope."""
    return participants.enrollment_owners(user)


def _row(p, names: dict, owners: dict) -> dict:
    pid = owners.get(p.enrollment_id)
    return {
        "id": str(p.pk),
        "participant_id": str(pid) if pid else None,
        "participant": names.get(pid, ""),
        "enrollment_id": str(p.enrollment_id),
        "employer_id": str(p.employer_id) if p.employer_id else None,
        "employer": p.employer.name if p.employer_id else p.employer_name_source,
        "linked": p.employer_id is not None,
        "designation": p.designation,
        "pathway": p.pathway,
        "pathway_label": PATHWAY_NAMES.get(p.pathway, ""),
        "status": p.status,
        "source_status": p.source_status,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "exit_reason": p.exit_reason,
        "current": placements.is_current(p),
        "verified": p.verified_on is not None,
        "verified_on": p.verified_on.isoformat() if p.verified_on else None,
        "verification_source": p.verification_source,
        "verification_source_label": SOURCE_NAMES.get(p.verification_source, ""),
        "imported": p.source_row_id is not None,
    }


def rows_for(user, placement_list, owners=None) -> list[dict]:
    owners = _owners(user) if owners is None else owners
    pids = {owners.get(p.enrollment_id) for p in placement_list} - {None}
    names = participants.names(pids)
    return [_row(p, names, owners) for p in placement_list]


def list_placements(user, *, pathway="", state="", employer_id=None, q="", participant_id=None,
                    offset=0, size=25) -> tuple[int, list[dict]]:  # fmt: skip
    owners = _owners(user)
    if participant_id:
        enrollments = [e for e, pid in owners.items() if str(pid) == str(participant_id)]
    else:
        enrollments = list(owners)
    name_hits = participants.matching_ids(user, q) if q else set()
    qs = placements.list_for(
        enrollments, pathway=pathway, state=state, employer_id=employer_id, q=q,
        q_enrollment_ids=[e for e, pid in owners.items() if pid in name_hits],
    )  # fmt: skip
    total = qs.count()
    return total, rows_for(user, list(qs[offset : offset + size]), owners)


def summary(user) -> dict:
    enrollments = list(_owners(user))
    out = {
        "total": placements.list_for(enrollments).count(),
        "current": placements.list_for(enrollments, state="current").count(),
        "ended": placements.list_for(enrollments, state="ended").count(),
        "unverified": placements.list_for(enrollments, state="unverified").count(),
        "by_pathway": {},
    }
    for code, label in placements.Placement.PATHWAYS:
        out["by_pathway"][code] = {
            "label": label,
            "current": placements.list_for(enrollments, pathway=code, state="current").count(),
        }
    return out


def get_placement(user, placement_id):
    """The episode, if its youth is inside the user's scope; otherwise NotFound."""
    try:
        p = placements.get(placement_id)
    except placements.PlacementError:
        raise NotFound from None
    if p.enrollment_id not in _owners(user):
        raise NotFound
    return p


def detail(user, p, *, can_edit: bool) -> dict:
    row = rows_for(user, [p])[0]
    return {
        **row,
        "benefits": p.benefits,
        "can": {
            "edit": can_edit and not row["imported"],
            "end": can_edit and p.end_date is None,
            "verify": can_edit,
        },
    }


def history(placement) -> list[dict]:
    return audit.history("placement", placement.pk)


def _wrap(call, **kwargs):
    try:
        return call(**kwargs)
    except placements.PlacementError as exc:
        raise Violation("", str(exc)) from exc


def _check_employer(employer_id):
    if employer_id and not employers.exists(employer_id):
        raise Violation("employer_id", "Employer not found.", "unknown_employer")


def _enrollment_for(user, participant_id, enrollment_id):
    if not participants.is_visible(user, participant_id):
        raise Violation("participant_id", "Youth not found.", "unknown_participant")
    own = [str(e) for e in participants.enrollment_ids(participant_id)]
    if enrollment_id:
        if str(enrollment_id) not in own:
            raise Violation(
                "enrollment_id", "That enrollment is not this youth's.", "bad_enrollment"
            )
        return enrollment_id
    if len(own) == 1:
        return own[0]
    if not own:
        raise Violation("enrollment_id", "This youth has no enrollment yet.", "no_enrollment")
    raise Violation(
        "enrollment_id", "Choose which enrollment this belongs to.", "choose_enrollment"
    )


def enrollment_choices(user, participant_id) -> list:
    if not participants.is_visible(user, participant_id):
        raise NotFound
    return [str(e) for e in participants.enrollment_ids(participant_id)]


def create_placement(*, actor, participant_id, enrollment_id=None, employer_id=None, **fields):
    _check_employer(employer_id)
    enrollment = _enrollment_for(actor, participant_id, enrollment_id)
    return _wrap(
        placements.record_manual, actor=actor, enrollment_id=enrollment,
        employer_id=employer_id, **fields,
    )  # fmt: skip


def update_placement(*, actor, placement, **changes):
    if changes.get("employer_id"):
        _check_employer(changes["employer_id"])
    return _wrap(placements.update_episode, actor=actor, placement_id=placement.pk, **changes)


def end_placement(*, actor, placement, end_date, exit_reason=""):
    return _wrap(
        placements.end_episode, actor=actor, placement_id=placement.pk, end_date=end_date,
        exit_reason=exit_reason,
    )  # fmt: skip


def verify_placement(*, actor, placement, source):
    return _wrap(placements.verify_episode, actor=actor, placement_id=placement.pk, source=source)


# --- the work queue (FR-22) ----------------------------------------------------------------------


def queue(user, *, mine: bool, today: date | None = None) -> dict:
    """What needs doing, in one place: interventions (overdue first), referrals waiting on staff,
    flagged youth and placements nobody has verified. ``mine`` limits interventions and
    referrals to those assigned to the user; flags and placements follow the user's scope."""
    today = today or timezone.localdate()
    now = timezone.now()
    counts = referrals.counts_for(user, mine=mine, today=today)
    waiting_total, waiting = referrals.queue_referrals(user, mine=mine, now=now)
    out = {
        "scope": "mine" if mine else "all",
        "today": today.isoformat(),
        "counts": {**counts, "referrals_waiting": waiting_total},
        "interventions": referrals.queue_interventions(user, mine=mine, today=today),
        "referrals": waiting,
        "flags": None,
        "placements_to_verify": None,
    }
    if has_permission(user, "intelligence.view"):
        ids = participants.visible_ids(user).values_list("pk", flat=True)
        q = intelligence.support_queue(ids, today, limit=FLAG_LIMIT)
        out["flags"] = {"total": q["counts"]["flagged"], "items": q["items"]}
        out["counts"]["flagged"] = q["counts"]["flagged"]
    if has_permission(user, "placements.view"):
        n = placements.unverified_count(list(_owners(user)))
        out["placements_to_verify"] = n
        out["counts"]["placements_to_verify"] = n
    return out
