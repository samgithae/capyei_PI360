"""Critical conflicts when two records of one youth are merged (NEW-077, D-081/B28).

Participants owns the merge but may not read placements, referrals or portal accounts (doc 04),
so this coordinator registers the checks at start-up and records the placement resolutions.
Nothing here closes, deletes or overwrites a placement on its own: an authorised officer
chooses, gives a reason, and the choice is kept with the merge."""

from django.db import transaction

from apps.participants import services as participants
from apps.placements import services as placements
from apps.portal import services as portal
from apps.referrals import services as referrals

TWO_RUNNING = "two_running_placements"
END, SAME = "end", "same"


def _running(youth_id):
    return list(
        placements.Placement.objects.filter(
            placements.RUNNING, enrollment__participant_id=youth_id
        ).select_related("employer")
    )


def _item(p, side):
    return {
        "id": str(p.pk),
        "side": side,
        "employer": p.employer.name if p.employer_id else p.employer_name_source,
        "pathway": p.pathway,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "designation": p.designation,
    }


def _same_looking(a, b):
    """A hint only, never acted on: same employer and the same start date."""
    name = lambda p: str(p.employer_id) if p.employer_id else p.employer_name_source.strip().lower()  # noqa: E731
    return name(a) == name(b) and a.start_date == b.start_date


def check(survivor, absorbed):
    found = []
    mine, theirs = _running(survivor.pk), _running(absorbed.pk)
    if mine and theirs:
        found.append(participants.conflict(
            TWO_RUNNING,
            "Both records have a running placement. A youth keeps at most one (B28).",
            items=[_item(p, "survivor") for p in mine] + [_item(p, "merged") for p in theirs],
            actions=[END, SAME],
            hint="Same placement recorded twice: keep one. Different placements: end the one "
            "that is over.",
        ) | {"looks_same": any(_same_looking(a, b) for a in mine for b in theirs)})  # fmt: skip
    a, b = referrals.active_opportunities(survivor.pk), referrals.active_opportunities(absorbed.pk)
    if both := sorted(set(a) & set(b)):
        found.append(participants.conflict(
            "same_opportunity_referral",
            "Both records have an active referral to the same opportunity.",
            items=[{"id": a[o], "side": "survivor"} for o in both]
            + [{"id": b[o], "side": "merged"} for o in both],
            hint="Withdraw or close one of the two referrals in Referrals first.",
        ))  # fmt: skip
    if portal.has_account(survivor.pk) and portal.has_account(absorbed.pk):
        found.append(participants.conflict(
            "two_portal_accounts",
            "Both records have a youth portal account; a youth keeps one.",
            hint="Ask an Administrator to close one of the two portal accounts first.",
        ))  # fmt: skip
    return found


class ResolutionError(Exception):
    def __init__(self, message, field="non_field_errors"):
        super().__init__(message)
        self.message, self.field = message, field


@transaction.atomic
def resolve_placements(
    *, actor, candidate, action, placement_id, reason, keep_id=None, end_date=None,
    exit_reason="",
):  # fmt: skip
    """Resolve two running placements on a pending merge. ``end``: the placements differ and
    this one is over (the officer gives the end date). ``same``: both rows are one real
    placement; this one is marked recorded twice and points at ``keep_id``."""
    if candidate.status != candidate.PENDING:
        raise ResolutionError("Only a merge pending resolution has conflicts to resolve.", "status")
    if not (reason or "").strip():
        raise ResolutionError("Give a reason.", "reason")
    pair = {candidate.participant_a_id, candidate.participant_b_id}
    running = {str(p.pk): p for y in pair for p in _running(y)}
    if str(placement_id) not in running:
        raise ResolutionError("Choose a running placement of one of the two records.", "placement")
    try:
        if action == END:
            placements.end_episode(
                actor=actor, placement_id=placement_id, end_date=end_date,
                exit_reason=exit_reason or reason,
            )  # fmt: skip
            detail = {"placement": str(placement_id), "end_date": str(end_date)}
        elif action == SAME:
            if str(keep_id) not in running:
                raise ResolutionError("Choose the running placement to keep.", "keep")
            placements.mark_recorded_twice(
                actor=actor, placement_id=placement_id, keep_id=keep_id, reason=reason
            )
            detail = {"placement": str(placement_id), "kept": str(keep_id)}
        else:
            raise ResolutionError("Unknown resolution.", "action")
    except placements.PlacementError as exc:
        raise ResolutionError(str(exc)) from exc
    try:
        return participants.resolve(
            actor=actor, candidate=candidate, conflict_code=TWO_RUNNING, action=action,
            reason=reason, detail=detail,
        )  # fmt: skip
    except participants.DuplicateFailure as exc:
        raise ResolutionError(exc.message, exc.field) from exc
