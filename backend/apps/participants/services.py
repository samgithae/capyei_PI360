"""Public interface of apps.participants.

``import_participant`` is what the import pipeline calls (T-040): it validates one normalised row
against reference data and, when asked, creates or updates the participant and enrolment. The
pipeline never touches participant models itself.
"""

from dataclasses import dataclass, field

from django.db import transaction

from apps.audit import services as audit
from apps.configuration import services as configuration

from . import corrections, review_flag
from . import cv as _cv
from . import cv_pdf as _cv_pdf
from . import photo as _photo
from .models import (
    Participant,
    ParticipantContact,
    ParticipantEnrollment,
    ParticipantResidence,
    SourceIdentifier,
)
from .photo import PhotoError  # noqa: F401
from .profile import (  # noqa: F401
    ProfileError,
    capability_snapshots,  # read by the compatibility rules
)
from .profile import options as profile_options  # noqa: F401
from .profile import read as read_profile  # noqa: F401
from .profile import write as write_profile  # noqa: F401
from .skill_views import catalogue as skill_catalogue  # noqa: F401

# Field -> required? The mapping templates target exactly these names.
FIELDS = {
    "full_name": True,
    "project_code": True,
    "cohort_code": True,
    "course_code": True,
    "enrollment_no": True,  # D-050: blocks with the name; match key for D-059
    "gender": False,
    "age": False,
    "county_code": False,
    "phone": False,
    "email": False,
    "status": False,
    "source_id": False,
}
EXTRA = "extra:"  # a mapping target: keep this column under its own label
MAX_EXTRA_LABEL, MAX_EXTRA_VALUE = 60, 500


def is_target(name: str) -> bool:
    """A valid mapping target: a core field, or ``extra:<label>`` for any other column."""
    return name in FIELDS or (
        name.startswith(EXTRA) and 0 < len(name[len(EXTRA) :].strip()) <= MAX_EXTRA_LABEL
    )


GENDERS = {"f": "female", "female": "female", "m": "male", "male": "male", "other": "other"}
IMPORT_RULES = [
    "A row is held (not loaded) if full name or enrollment number is missing (D-050), or if "
    "project, cohort or course is missing or not in the reference data (an enrollment cannot "
    "exist without them).",
    "A row matches an existing record on project + enrollment number; matched rows are "
    "skipped, never updated (D-059: imports add new people only).",
    "Unknown county, gender or age become blank/unknown with a warning; they never block a row.",
    "Rows already loaded from an earlier file (same key and content) are skipped.",
    "Possible duplicates found after a load are queued for a steward and are never merged "
    "automatically.",
]  # Rules are proposals until D-004/D-005 are settled.
STATUSES = {"active": "enrolled", "enrolled": "enrolled", "completed": "completed",
            "withdrawn": "withdrawn"}  # fmt: skip


@dataclass
class Checked:
    """Result of checking one row. ``errors`` block the row; ``warnings`` do not."""

    clean: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)  # [{"field", "message"}]
    warnings: list = field(default_factory=list)
    source_key: str = ""
    match: str = "new"  # new | exact (same project + enrollment number already loaded)
    diff: list = field(default_factory=list)  # [{"field","current","incoming"}] for exact matches


def _text(raw, key):
    return str(raw.get(key, "") or "").strip()


def check_row(raw: dict) -> Checked:
    out = Checked()
    err = lambda f, m: out.errors.append({"field": f, "message": m})  # noqa: E731
    warn = lambda f, m: out.warnings.append({"field": f, "message": m})  # noqa: E731
    c = out.clean
    c["extra"] = {
        k[len(EXTRA) :].strip(): _text(raw, k)[:MAX_EXTRA_VALUE]
        for k in raw
        if k.startswith(EXTRA) and _text(raw, k)
    }
    for f, required in FIELDS.items():
        c[f] = _text(raw, f)
        if required and not c[f]:
            err(f, "Required.")

    offering_id, prog_id, _inst, problems = configuration.resolve_offering(
        c["project_code"], c["cohort_code"], c["course_code"]
    )
    county_id = None
    if c["county_code"]:
        county_id = configuration.county_id_by_code(c["county_code"])
        if county_id is None:
            warn("county_code", f"Unknown county '{c['county_code']}'; left blank.")
    fixable = {"cohort_code", "course_code"}
    if problems and {f for f, _m in problems} <= fixable:
        # The centre, cohort or course is just not in reference data yet: propose creating it
        # instead of blocking. Nothing is created until the batch is approved.
        proposal = configuration.propose_reference(
            c["project_code"], c["cohort_code"], c["course_code"], county_id
        )
        if proposal:
            problems = []
            c["_proposed"] = proposal
            made = ", ".join(f"{i['kind'][:-1].replace('-', ' ')} {i['label']}" for i in proposal)
            warn("cohort_code", f"New reference data will be created on approval: {made}.")
    for f, m in problems:
        err(f, m)
    if c["phone"]:  # spec 15 §4: a warning, never a rewrite (rule N-03 is a proposal)
        digits = sum(ch.isdigit() for ch in c["phone"])
        if digits == 9:
            warn("phone", "Phone has 9 digits; a leading 0 may be missing. Stored as received.")
        elif digits != 10:
            warn("phone", f"Phone has {digits} digits; 10 expected. Stored as received.")
    if c["gender"]:
        g = GENDERS.get(c["gender"].lower())
        if g is None:
            warn("gender", f"Unrecognised gender '{c['gender']}'; stored as unknown.")
        c["gender"] = g or "unknown"
    else:
        c["gender"] = "unknown"
    if c["age"]:
        try:
            age = int(float(c["age"]))
            if not 10 <= age <= 100:
                raise ValueError
            c["age"] = age
        except ValueError:
            warn("age", f"Age '{c['age']}' is not usable; left blank.")
            c["age"] = None
    else:
        c["age"] = None
    c["status"] = STATUSES.get(c["status"].lower(), "unknown")

    if prog_id and c["enrollment_no"]:
        out.source_key = f"{c['project_code'].upper()}|{c['enrollment_no']}"
        existing = (
            ParticipantEnrollment.objects.select_related("participant__origin_county")
            .filter(project_id=prog_id, source_enrollment_no=c["enrollment_no"])
            .first()
        )
        if existing:
            out.match = "exact"
            out.diff = _diff(existing, c)
    c["_refs"] = {
        "offering": offering_id,
        "project": prog_id,
        "county": county_id,
    }
    return out


def _diff(e: ParticipantEnrollment, c: dict) -> list:
    """Field-by-field differences between the stored person and the file row (spec 15 §5).

    Read-only: D-059 means imports never update, so this is information for the steward. A field
    is compared only when the file actually supplies a usable value, so blanks and "unknown"
    never show as differences."""
    p = e.participant
    phone = p.contacts.filter(kind="phone").values_list("value", flat=True).first() or ""
    email = p.contacts.filter(kind="email").values_list("value", flat=True).first() or ""
    pairs = [
        ("full_name", p.full_name_source, c["full_name"]),
        ("gender", p.gender, c["gender"] if c["gender"] != "unknown" else None),
        ("age", p.age_at_source, c["age"]),
        ("status", e.status, c["status"] if c["status"] != "unknown" else None),
        ("county_code", p.origin_county.code if p.origin_county else "", c["county_code"] or None),
        ("phone", phone, c["phone"] or None),
        ("email", email, c["email"] or None),
    ]
    return [
        {"field": f, "current": "" if cur is None else str(cur), "incoming": str(new)}
        for f, cur, new in pairs
        if new is not None
        and str(cur if cur is not None else "").strip().lower() != str(new).strip().lower()
    ]


def _snapshot(p: Participant, e: ParticipantEnrollment) -> dict:
    return {
        "full_name": p.full_name_source,
        "gender": p.gender,
        "age": p.age_at_source,
        "status": e.status,
        "county": str(p.origin_county_id or ""),
    }


def import_owner(actor):
    """Who youth created by this user's import are assigned to. A user limited to their own
    caseload (a placement officer) gets what they import, or they could not see it afterwards.
    An organisation-wide user (steward, administrator) already sees everything, so no one."""
    from apps.api import access

    limited = bool(access.scope_q(actor, {"officer": "assigned_officer_id"}))
    return actor if limited and getattr(actor, "pk", None) else None


@transaction.atomic
def import_participant(clean: dict, *, batch_ref: str, owner=None) -> tuple[str, str, dict, dict]:
    """Create or update. Returns (action, participant_id, before, after).
    ``owner`` becomes the assigned officer of a newly created youth (see ``import_owner``).

    Matching is deterministic: project + enrollment number. A field an officer has corrected
    since the last import is protected (R-15, D-005; see ``corrections.guard_import``).
    """
    refs = clean["_refs"]
    offering_id, _p, institution_id, _e = configuration.resolve_offering(
        clean["project_code"], clean["cohort_code"], clean["course_code"]
    )
    existing = None
    if clean["enrollment_no"]:
        existing = (
            ParticipantEnrollment.objects.select_related("participant")
            .filter(project_id=refs["project"], source_enrollment_no=clean["enrollment_no"])
            .first()
        )
    if existing:
        p, e = existing.participant, existing
        before = _snapshot(p, e)
        # Fields an officer has corrected here are not overwritten (R-15, D-005, D-025): a
        # file value that matches closes the correction, one that differs is held for review.
        incoming = {"full_name": clean["full_name"]}
        if clean["gender"] != "unknown":
            incoming["gender"] = clean["gender"]
        if clean["age"] is not None:
            incoming["age"] = clean["age"]
        if refs["county"]:
            incoming["county"] = refs["county"]
        if clean["status"] != "unknown":
            incoming["status"] = clean["status"]
        held = corrections.guard_import(p, e, incoming, batch_ref=batch_ref)
        if "full_name" not in held:
            p.full_name_source = clean["full_name"]
        if clean["gender"] != "unknown" and "gender" not in held:
            p.gender = clean["gender"]
        if clean["age"] is not None and "age" not in held:
            p.age_at_source = clean["age"]
        if refs["county"] and "county" not in held:
            p.origin_county_id = refs["county"]
        p.save()
        if clean["status"] != "unknown" and "status" not in held:
            e.status = clean["status"]
            e.save()
        after = _snapshot(p, e)
        if any(before.get(k) != after.get(k) for k in ("full_name", "gender", "age", "county")):
            review_flag.flag(p=p, reason=review_flag.IMPORT_CHANGE)
        return "update", str(p.pk), before, after

    p = Participant.objects.create(
        full_name_source=clean["full_name"],
        gender=clean["gender"],
        age_at_source=clean["age"],
        origin_county_id=refs["county"],
        assigned_officer=owner,
    )
    e = ParticipantEnrollment.objects.create(
        participant=p,
        cohort_course_id=offering_id or refs["offering"],
        project_id=refs["project"],
        institution_id=institution_id,
        source_enrollment_no=clean["enrollment_no"],
        status=clean["status"],
        extra=clean.get("extra") or {},
    )
    if clean["phone"]:
        ParticipantContact.objects.create(
            participant=p, kind="phone", value=clean["phone"], is_primary=True
        )
    if clean["email"]:
        ParticipantContact.objects.create(
            participant=p, kind="email", value=clean["email"], is_primary=True
        )
    if clean["source_id"]:
        SourceIdentifier.objects.create(
            participant=p, source=f"import:{batch_ref[:8]}", identifier=clean["source_id"]
        )
    return "create", str(p.pk), {}, _snapshot(p, e)


@transaction.atomic
def undo_import(*, action: str, participant_id: str, before: dict) -> None:
    """Reverse one lineage entry: delete what an import created, restore what it changed."""
    p = Participant.objects.filter(pk=participant_id).first()
    if p is None:
        return
    if action == "create":
        p.delete()  # enrollments, contacts and identifiers cascade
        return
    p.full_name_source = before["full_name"]
    p.gender = before["gender"]
    p.age_at_source = before["age"]
    p.origin_county_id = before["county"] or None
    p.save()
    e = p.enrollments.first()
    if e:
        e.status = before["status"]
        e.save()


# Duplicate detection and merge (T-041) live in duplicates.py; other modules import them from here.
from .duplicates import (  # noqa: E402
    DuplicateFailure,
    add_check,
    cohort_counts,
    complete,
    conflict,
    dismiss,
    find_pairs,
    get_candidate,  # noqa: F401 (re-exported for casework)
    involved_in_merge,
    merge,
    quarantined,
    resolve,
    review,
    scan,
    unmerge,
)

# --- the youth directory: one filter for the table and for its export (T-071) -------------------


class FilterError(ValueError):
    """A filter value that is not a valid id."""


def current_age(p: Participant):
    """Age today from the date of birth; the source file's age only when there is none."""
    from django.utils import timezone

    dob = p.date_of_birth
    if not dob:
        return p.age_at_source
    today = timezone.localdate()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def filtered(user, params):
    """``(queryset, fuzzy)`` for the directory filters in ``params`` (a query dict), scoped to the
    caller. The list page and its export both use this, so the file is exactly the table."""
    import uuid

    from . import similar

    qs = Participant.objects.visible_to(user, archived=params.get("archived") == "1")
    try:
        if params.get("project"):
            qs = qs.filter(enrollments__project_id=uuid.UUID(params["project"]))
        if params.get("cohort"):
            qs = qs.filter(enrollments__cohort_course__cohort_id=uuid.UUID(params["cohort"]))
        if params.get("county"):
            qs = qs.filter(origin_county_id=uuid.UUID(params["county"]))
    except ValueError:
        raise FilterError("Invalid filter value.") from None
    if params.get("status") in {s for s, _ in Participant.STATUSES}:
        qs = qs.filter(status=params["status"])
    if params.get("review") == Participant.REVIEW_NEEDED:  # NEW-051: the review work list
        qs = qs.filter(review_state=Participant.REVIEW_NEEDED)
    fuzzy = False
    if q := params.get("q", "").strip():
        qs, fuzzy = similar.search(qs, q)
    return qs.distinct().order_by("full_name_source", "pk"), fuzzy


CONSENT_FLAG = "consent_tracking"  # off until an administrator turns it on (T-054)


def consent_enabled() -> bool:
    return configuration.is_enabled(CONSENT_FLAG)


def flag_enabled(key, user=None) -> bool:
    """Whether a feature flag is on for this user; lets the portal gate routes without importing
    configuration."""
    return configuration.is_enabled(key, user)


def export_groups() -> list[dict]:
    """The youth fields an export can hold, grouped, for the field picker. The consent group is
    left out while the consent setting is off."""
    from . import export_fields

    on = consent_enabled()
    return [g for g in export_fields.groups() if on or g["key"] != "consent"]


def export_rows(user, params, keys) -> list[dict]:
    """One row per youth in the directory under ``params``, holding ``_id`` and each requested
    field this module owns. Same filter and scope as the table, so the file matches the screen."""
    from . import export_fields

    qs, _fuzzy = filtered(user, params)
    if not consent_enabled():
        keys = [k for k in keys if k not in export_fields.CONSENT_KEYS]
    return export_fields.rows(qs, keys)


def export_corrections(user, params, keys) -> list[dict]:
    """Rows for the corrections export (T-074): the fixes waiting for the MIS, by default."""
    return corrections.export_rows(user, params, keys)


__all__ = [
    "export_corrections",
    "FilterError",
    "current_age",
    "export_groups",
    "export_rows",
    "filtered",
    "DuplicateFailure",
    "PhotoError",
    "ProfileError",
    "build_cv",
    "cohort_counts",
    "cv_pdf",
    "get_photo",
    "remove_photo",
    "save_photo",
    "dismiss",
    "display_name",
    "email_addresses",
    "find_active",
    "profile_options",
    "profile_serializer",
    "read_profile",
    "write_profile",
    "find_pairs",
    "involved_in_merge",
    "merge",
    "add_check",
    "complete",
    "conflict",
    "resolve",
    "review",
    "quarantined",
    "scan",
    "unmerge",
]


def create_proposed_reference(*, actor, items):
    """Create the centres, courses, cohorts and offerings an import proposed (see check_row)."""
    try:
        return configuration.create_proposed(actor=actor, items=items)
    except configuration.ConfigError as exc:
        raise ValueError(exc.message) from exc


def offering_resolves(clean: dict) -> list:
    """Problems (``[(field, message)]``) still stopping this row's cohort/course resolving."""
    return configuration.resolve_offering(
        clean["project_code"], clean["cohort_code"], clean["course_code"]
    )[3]


def reference_codes():
    """Project, cohort and course codes people can type or pick when importing."""
    return configuration.reference_codes()


def find_enrollment(project_code, enrollment_no):
    """Id of the enrollment with this project code and source enrollment number, or None.
    Lets other modules (the placement import) attach records without touching our models."""
    code, no = (project_code or "").strip(), (enrollment_no or "").strip()
    if not code or not no:
        return None
    pk = (
        ParticipantEnrollment.objects.filter(project__code__iexact=code, source_enrollment_no=no)
        .values_list("pk", flat=True)
        .first()
    )
    return str(pk) if pk else None


def extra_labels(project_code):
    """The ``extra`` labels held on enrollments of one project, with how many have a value.
    Also counts enrollments with no source enrollment number (they cannot be matched later)."""
    labels: dict[str, int] = {}
    qs = ParticipantEnrollment.objects.filter(project__code__iexact=(project_code or "").strip())
    total = no_number = 0
    for no, extra in qs.values_list("source_enrollment_no", "extra").iterator():
        total += 1
        no_number += not no
        for k, v in (extra or {}).items():
            if str(v).strip():
                labels[k] = labels.get(k, 0) + 1
    return {
        "enrollments": total,
        "without_number": no_number,
        "labels": [{"label": k, "filled": n} for k, n in sorted(labels.items())],
    }


def extra_rows(project_code, labels):
    """(source enrollment number, {label: value}) for enrollments that have a number and at least
    one of ``labels`` filled. Read-only; the caller turns these into an import file."""
    qs = (
        ParticipantEnrollment.objects.filter(project__code__iexact=(project_code or "").strip())
        .exclude(source_enrollment_no="")
        .order_by("source_enrollment_no")
    )
    for no, extra in qs.values_list("source_enrollment_no", "extra").iterator():
        got = {k: str(extra[k]).strip() for k in labels if str((extra or {}).get(k, "")).strip()}
        if got:
            yield no, got


# --- for other modules (T-046 referrals) ---------------------------------------------------


def visible_ids(user):
    """Ids of participants the user may see (scope applied; merged and archived hidden).
    A queryset, so callers can use it as a subquery: ``filter(participant_id__in=...)``."""
    return Participant.objects.visible_to(user).values("pk")


def is_visible(user, participant_id) -> bool:
    return Participant.objects.visible_to(user).filter(pk=participant_id).exists()


def matching_ids(user, text) -> set:
    """Ids of visible youth whose name contains ``text`` (for list searches in other modules)."""
    text = (text or "").strip()
    if not text:
        return set()
    return set(
        Participant.objects.visible_to(user)
        .filter(full_name_source__icontains=text)
        .values_list("pk", flat=True)
    )


class CreateError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field, self.message = field, message


@transaction.atomic
def create_participant(*, actor, data: dict) -> Participant:
    """Add one youth by hand (the import is the bulk route), with every optional detail.
    The creator becomes the assigned officer so an officer-scoped user can still see the
    record they just added. The enrollment, when given, is by cohort offering; the project and
    institution come from the cohort."""
    from django.utils import timezone

    enr = data.get("enrollment")
    ids = None
    if enr:
        ids = configuration.offering_ids(enr["cohort_course_id"])
        if ids is None:
            raise CreateError("enrollment", "Unknown course offering.")
        no = enr.get("enrollment_no", "").strip()
        if (
            no
            and ParticipantEnrollment.objects.filter(
                project_id=ids[0], source_enrollment_no=no
            ).exists()
        ):
            raise CreateError("enrollment", "Another enrollment in this project has that number.")
    if (sid := data.get("source_id")) and SourceIdentifier.objects.filter(
        source=data["source_name"].strip(), identifier=sid.strip()
    ).exists():
        raise CreateError("source_id", "Someone already has that ID from that system.")
    p = Participant.objects.create(
        full_name_source=data["full_name_source"].strip(),
        given_name=data.get("given_name", ""),
        family_name=data.get("family_name", ""),
        other_names=data.get("other_names", ""),
        gender=data.get("gender", Participant.GENDER_UNKNOWN),
        status=data.get("status", Participant.UNKNOWN),
        age_at_source=data.get("age_at_source"),
        age_basis_date=data.get("age_basis_date"),
        date_of_birth=data.get("date_of_birth"),
        origin_county_id=data.get("origin_county_id"),
        assigned_officer=actor if getattr(actor, "pk", None) else None,
    )
    if enr:
        ParticipantEnrollment.objects.create(
            participant=p,
            cohort_course_id=enr["cohort_course_id"],
            project_id=ids[0],
            institution_id=ids[1],
            source_enrollment_no=enr.get("enrollment_no", "").strip(),
            status=enr.get("status", ParticipantEnrollment.ENROLLED),
            enrolled_on=enr.get("enrolled_on"),
            completed_on=enr.get("completed_on"),
            exit_reason=enr.get("exit_reason", ""),
            source_qualification_code=enr.get("qualification_code", ""),
            referral_source_code=enr.get("referral_source_code", ""),
            extra=enr.get("extra") or {},
        )
    res = data.get("residence") or {}
    if res.get("county_id") or res.get("sub_county") or res.get("ward"):
        ParticipantResidence.objects.create(
            participant=p,
            county_id=res.get("county_id"),
            sub_county_source=res.get("sub_county", ""),
            ward_source=res.get("ward", ""),
            valid_from=timezone.localdate(),
        )
    contacts = data.get("contacts") or []
    for c in contacts:
        ParticipantContact.objects.create(
            participant=p, kind=c["kind"], value=c["value"].strip(), is_primary=c["primary"]
        )
    if sid:
        SourceIdentifier.objects.create(
            participant=p, source=data["source_name"].strip(), identifier=sid.strip()
        )
    capability = data.get("capability")
    if capability:
        try:
            write_profile(actor=actor, p=p, data=capability)
        except ProfileError as exc:
            raise CreateError(exc.field, str(exc)) from exc
    audit.record(
        actor=actor,
        action="participant.created",
        object_type="participant",
        object_id=p.pk,
        after={
            "gender": p.gender,
            "status": p.status,
            "county_id": str(p.origin_county_id) if p.origin_county_id else None,
            "enrolled": enr is not None,
            "residence": bool(res),
            "contact_kinds": [c["kind"] for c in contacts],  # kinds only, never the values
        },
    )
    return p


# ---- what the youth portal needs (it may not touch participant models) -----------------------


def find_active(participant_id):
    """The participant, or None when missing, merged or archived."""
    try:
        return Participant.objects.get(
            pk=participant_id, merged_into__isnull=True, archived_at__isnull=True
        )
    except (Participant.DoesNotExist, ValueError):
        return None


def email_addresses(p: Participant) -> list[str]:
    return list(
        p.contacts.filter(kind=ParticipantContact.EMAIL)
        .order_by("-is_primary", "created_at")
        .values_list("value", flat=True)
    )


def profile_serializer():
    """The request serializer of the capability profile (shared with the youth portal)."""
    from .profile_views import ProfileSerializer  # noqa: PLC0415

    return ProfileSerializer


def display_name(p: Participant) -> str:
    return str(p)


def names(ids) -> dict:
    """``{id: display name}`` for a batch of youth."""
    return {p.pk: str(p) for p in Participant.objects.filter(pk__in=list(ids))}


def ready_since(ids, today) -> dict:
    """``{id: date}`` for enrolled or completed youth who said they can start work, and from
    when. Those with no availability recorded are left out: that is missing, not "not ready"."""
    from .models import ParticipantEnrollment, ParticipantReadiness

    rows = ParticipantReadiness.objects.filter(
        participant_id__in=list(ids), available_from__isnull=False, available_from__lte=today
    ).filter(
        participant__enrollments__status__in=[
            ParticipantEnrollment.ENROLLED,
            ParticipantEnrollment.COMPLETED,
        ]
    )
    return dict(rows.values_list("participant_id", "available_from").distinct())


from .models import Participant as _P  # noqa: E402
from .self_details import DetailsError  # noqa: E402,F401
from .self_details import read_own as read_own_details  # noqa: E402,F401
from .self_details import write_own as write_own_details  # noqa: E402,F401

GENDER_CHOICES = _P.GENDERS


def enrollment_ids(participant_id) -> list:
    """Ids of a participant's enrollments (for modules that hold records per enrollment)."""
    return list(
        _P.enrollments.rel.related_model.objects.filter(participant_id=participant_id).values_list(
            "pk", flat=True
        )
    )


# --- for reporting (T-070): plain facts, scope applied, no names ----------------------------------


def report_facts(user) -> list[dict]:
    """One small dict per youth the user may see: the fields the dashboard groups by."""
    rows = Participant.objects.visible_to(user).values_list(
        "pk",
        "gender",
        "status",
        "origin_county_id",
        "origin_county__name",
        "date_of_birth",
        "age_at_source",
        "age_basis_date",
        "created_at",
    )
    return [
        {
            "id": r[0],
            "gender": r[1],
            "status": r[2],
            "county_id": r[3],
            "county": r[4],
            "dob": r[5],
            "age_at_source": r[6],
            "age_basis": r[7],
            "created_at": r[8],
        }
        for r in rows
    ]


def report_options() -> dict:
    """The project, cohort, institution, county and sector lists the report filters offer
    (reporting reaches configuration through here)."""
    return configuration.report_options()


def enrollment_facts(user) -> list[dict]:
    """One small dict per enrolment of a youth the user may see: what the reports group by."""
    from .models import ParticipantEnrollment

    rows = ParticipantEnrollment.objects.filter(participant_id__in=visible_ids(user)).values_list(
        "pk",
        "participant_id",
        "project_id",
        "cohort_course__cohort_id",
        "institution_id",
        "status",
        "enrolled_on",
    )
    return [
        {
            "id": r[0],
            "participant_id": r[1],
            "project_id": r[2],
            "cohort_id": r[3],
            "institution_id": r[4],
            "status": r[5],
            "enrolled_on": r[6],
        }
        for r in rows
    ]


def enrollment_owners(user) -> dict:
    """``{enrollment id: participant id}`` for youth the user may see."""
    from .models import ParticipantEnrollment

    return dict(
        ParticipantEnrollment.objects.filter(participant_id__in=visible_ids(user)).values_list(
            "pk", "participant_id"
        )
    )


def brief(ids) -> dict:
    """``{id: {name, detail}}`` for a page of youth in a drill-down list."""
    out = {}
    for p in Participant.objects.filter(pk__in=list(ids)).select_related("origin_county"):
        bits = [p.get_gender_display(), p.origin_county.name if p.origin_county_id else ""]
        out[p.pk] = {
            "name": str(p),
            "detail": " · ".join(b for b in bits if b and b != "Unknown"),
        }
    return out


def build_cv(p: Participant, *, include_contact: bool = True) -> dict:
    """The CV document of a youth, from what is saved now (see ``cv.build``)."""
    return _cv.build(p, include_contact=include_contact, has_photo=_photo.has(p))


def cv_pdf(*, actor, p: Participant, include_contact: bool = True) -> tuple[bytes, str]:
    """``(pdf bytes, file name)``. Built from the saved records at the moment of the call."""
    doc = build_cv(p, include_contact=include_contact)
    data = _cv_pdf.render(doc, _photo.get(p))
    audit.record(
        actor=actor,
        action="participant.cv_downloaded",
        object_type="participant",
        object_id=p.pk,
        after={"bytes": len(data)},
    )
    return data, _cv.filename(doc["name"])


def get_photo(p: Participant) -> bytes | None:
    return _photo.get(p)


def save_photo(*, actor, p: Participant, raw: bytes) -> None:
    _photo.save(actor=actor, p=p, raw=raw)


def remove_photo(*, actor, p: Participant) -> None:
    _photo.remove(actor=actor, p=p)


# ---- for the self-registration review (NEW-046) ----------------------------------------------


def similar_visible(user, *, name, phone="", birth_date=None) -> list[dict]:
    """People the user may see who look like this sign-up (never the matched phone or date)."""
    from . import similar

    return similar.similar_to(
        name=name, scope=Participant.objects.visible_to(user), phone=phone, birth_date=birth_date
    )


def create_from_signup(*, actor, req_data: dict) -> Participant:
    """A new youth record from an approved sign-up. Only what the youth gave is copied: name,
    date of birth, gender when it is one of ours, and the contacts. A programme or enrolment
    number they claimed is not turned into an enrolment (it is unverified)."""
    given, family = req_data["given_name"].strip(), req_data["family_name"].strip()
    gender = req_data.get("gender", "")
    contacts = []
    if req_data.get("email"):
        contacts.append({"kind": "email", "value": req_data["email"], "primary": True})
    if req_data.get("phone"):
        contacts.append({"kind": "phone", "value": req_data["phone"], "primary": not contacts})
    return create_participant(
        actor=actor,
        data={
            "full_name_source": f"{given} {family}".strip(),
            "given_name": given,
            "family_name": family,
            "gender": gender if gender in dict(Participant.GENDERS) else Participant.GENDER_UNKNOWN,
            "date_of_birth": req_data.get("date_of_birth"),
            "contacts": contacts,
        },
    )


# The review flag (D-084, NEW-050) lives in review.py; other modules import it from here.
flag_for_review = review_flag.flag
review_history = review_flag.history
mark_reviewed = review_flag.mark_reviewed
officer_flag = review_flag.officer_flag
ReviewError = review_flag.ReviewError
