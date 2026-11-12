"""Public interface of apps.configuration: reference data, feature flags, protected settings.
Other modules import only this module. Every change is audited in the same transaction."""

import json
import re
import uuid
from pathlib import Path

from django.conf import settings as dj_settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.api import access
from apps.audit import services as audit

from .models import (
    County,
    FeatureFlag,
    ProtectedSetting,
    ReferenceAlias,
    ReferenceLabel,
    SubCounty,
    Ward,
    norm,
)
from .reference import KINDS, OPTIONAL_FKS
from .seed import COUNTIES


class ConfigError(ValueError):
    """A rule was broken. ``field`` names the input at fault."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field, self.message = field, message


# --- seeding ---------------------------------------------------------------


def ensure_seed_data() -> None:
    for code, name in COUNTIES:
        County.objects.get_or_create(code=code, defaults={"name": name})
    _seed_geography()


def _seed_geography() -> None:
    """Sub-counties and wards from ``geography.json`` (IEBC constituencies and their wards).

    The sub-county level uses the 290 constituencies because wards are published under them.
    Adds what is missing and never edits or removes anything, so renames, retirements and
    records added by hand survive; it is safe to run on every migrate."""
    data = json.loads((Path(__file__).parent / "geography.json").read_text(encoding="utf-8"))
    counties = {c.code: c for c in County.objects.all()}
    have_subs = {(s.county_id, s.name_normalised) for s in SubCounty.objects.all()}
    new_subs = []
    for ccode, subs in data.items():
        county = counties.get(ccode)
        if county is None:
            continue
        for scode, sname, _ in subs:
            if (county.id, norm(sname)) in have_subs:
                continue
            new_subs.append(
                SubCounty(county=county, code=scode, name=sname, name_normalised=norm(sname))
            )
    SubCounty.objects.bulk_create(new_subs)
    sub_ids = {(s.county_id, s.name_normalised): s.id for s in SubCounty.objects.all()}
    have_wards = {(w.sub_county_id, w.name_normalised) for w in Ward.objects.all()}
    new_wards = []
    for ccode, subs in data.items():
        county = counties.get(ccode)
        if county is None:
            continue
        for _, sname, wards in subs:
            sub_id = sub_ids.get((county.id, norm(sname)))
            if sub_id is None:
                continue
            for wcode, wname in wards:
                if (sub_id, norm(wname)) in have_wards:
                    continue
                new_wards.append(
                    Ward(sub_county_id=sub_id, code=wcode, name=wname, name_normalised=norm(wname))
                )
    Ward.objects.bulk_create(new_wards)


# --- reference data (T-057) ------------------------------------------------


def kind_of(key):
    if key not in KINDS:
        raise ConfigError("kind", f"Unknown reference kind: {key}")
    return KINDS[key]


def _snapshot(obj, kind):
    names = (["code", "name"] if kind.named else []) + list(kind.fields) + list(kind.fks)
    out = {}
    for n in names:
        v = getattr(obj, n + "_id") if n in kind.fks else getattr(obj, n)
        out[n] = None if v is None else str(v)
    out["active"] = obj.active
    return out


def _resolve_fks(kind, data):
    resolved = {}
    for name, parent_key in kind.fks.items():
        if name not in data:
            continue
        raw = data[name]
        if raw in (None, "") and name in OPTIONAL_FKS:
            resolved[name] = None
            continue
        try:
            resolved[name] = KINDS[parent_key].model.objects.get(pk=uuid.UUID(str(raw)))
        except (ValueError, KINDS[parent_key].model.DoesNotExist):
            raise ConfigError(name, f"Unknown {KINDS[parent_key].label.lower()}.") from None
    return resolved


def _clean(obj):
    try:
        obj.full_clean(exclude=["name_normalised"] if hasattr(obj, "name_normalised") else None)
    except DjangoValidationError as exc:
        field_name, messages = next(iter(exc.message_dict.items()))
        raise ConfigError("name" if field_name == "__all__" else field_name, messages[0]) from exc


@transaction.atomic
def create_reference(*, actor, key, data):
    kind = kind_of(key)
    if not kind.creatable:
        raise ConfigError("kind", f"{kind.label} records are seeded and cannot be added.")
    values = {f: data[f] for f in kind.fields if f in data}
    if kind.named:
        values["code"] = str(data.get("code", "")).strip()
        values["name"] = str(data.get("name", "")).strip()
        if not values["code"] or not values["name"]:
            raise ConfigError("code", "A code and a name are required.")
    obj = kind.model(**values, **_resolve_fks(kind, data))
    _clean(obj)
    try:
        with transaction.atomic():
            obj.save()
    except IntegrityError as exc:
        raise ConfigError("code", "This record already exists.") from exc
    if kind.named:
        ReferenceLabel.objects.create(
            kind=key, object_id=obj.pk, name=obj.name, changed_by=_user(actor)
        )
    audit.record(
        actor=actor,
        action="reference.created",
        object_type=f"reference.{key}",
        object_id=obj.pk,
        after=_snapshot(obj, kind),
    )
    return obj


@transaction.atomic
def update_reference(*, actor, key, obj, data):
    kind = kind_of(key)
    if "code" in data and kind.named and str(data["code"]).strip() != obj.code:
        raise ConfigError(
            "code", "A code is stable and cannot be changed. Add a new record instead."
        )
    before = _snapshot(obj, kind)
    for f in kind.fields:
        if f in data:
            setattr(obj, f, data[f])
    for name, parent in _resolve_fks(kind, data).items():
        setattr(obj, name, parent)
    renamed = kind.named and "name" in data and str(data["name"]).strip() != obj.name
    if renamed:
        obj.name = str(data["name"]).strip()
    _clean(obj)
    after = _snapshot(obj, kind)
    if after == before:
        return obj
    try:
        with transaction.atomic():
            obj.save()
    except IntegrityError as exc:
        raise ConfigError("name", "This record already exists.") from exc
    if renamed:
        ReferenceLabel.objects.create(
            kind=key, object_id=obj.pk, name=obj.name, changed_by=_user(actor)
        )
    audit.record(
        actor=actor,
        action="reference.changed",
        object_type=f"reference.{key}",
        object_id=obj.pk,
        before=before,
        after=after,
    )
    return obj


@transaction.atomic
def set_reference_active(*, actor, key, obj, active, reason=""):
    if obj.active == active:
        return obj
    obj.active = active
    obj.save(update_fields=["active", "updated_at"] if hasattr(obj, "updated_at") else ["active"])
    audit.record(
        actor=actor,
        action="reference.reactivated" if active else "reference.deactivated",
        object_type=f"reference.{key}",
        object_id=obj.pk,
        before={"active": not active},
        after={"active": active},
        reason=reason,
    )
    return obj


@transaction.atomic
def add_alias(*, actor, key, obj, alias, source="", scope=""):
    if not alias.strip():
        raise ConfigError("alias", "An alias cannot be empty.")
    if ReferenceAlias.objects.filter(kind=key, scope=scope, alias_normalised=norm(alias)).exists():
        raise ConfigError("alias", "This spelling already resolves to a record.")
    row = ReferenceAlias.objects.create(
        kind=key,
        object_id=obj.pk,
        scope=scope,
        alias=alias.strip(),
        source=source,
        approved_by=_user(actor),
    )
    audit.record(
        actor=actor,
        action="reference.alias_added",
        object_type=f"reference.{key}",
        object_id=obj.pk,
        after={"alias": row.alias},
    )
    return row


def resolve(key, text, scope=""):
    """Find the record a source spelling refers to (name or approved alias), or None."""
    kind = kind_of(key)
    n = norm(text)
    if not n:
        return None
    hit = kind.model.objects.filter(name_normalised=n)
    if scope:
        hit = hit.filter(**{kind_scope_field(kind): scope})
    obj = hit.first()
    if obj:
        return obj
    alias = ReferenceAlias.objects.filter(kind=key, scope=scope, alias_normalised=n).first()
    return kind.model.objects.filter(pk=alias.object_id).first() if alias else None


def kind_scope_field(kind):
    return next(iter(kind.fks), "pk") + "_id" if kind.fks else "pk"


def _user(actor):
    return actor if getattr(actor, "pk", None) else None


# --- feature flags (T-039) -------------------------------------------------


def current_environment() -> str:
    return dj_settings.APP_ENV


def is_enabled(key, user=None) -> bool:
    """Off unless a flag row exists, is on, and the environment and role audience match."""
    flag = FeatureFlag.objects.filter(key=key).first()
    if flag is None or not flag.enabled:
        return False
    if flag.environments and current_environment() not in flag.environments:
        return False
    if flag.roles:
        return bool(set(flag.roles) & set(access.roles_of(user))) if user else False
    return True


def _flag_snapshot(flag):
    return {
        "enabled": flag.enabled,
        "environments": flag.environments,
        "roles": flag.roles,
        "description": flag.description,
    }


@transaction.atomic
def set_flag(
    *, actor, key, enabled=None, environments=None, roles=None, description=None, reason=""
):
    flag, created = FeatureFlag.objects.get_or_create(key=key)
    before = None if created else _flag_snapshot(flag)
    if enabled is not None:
        flag.enabled = enabled
    if environments is not None:
        flag.environments = sorted(set(environments))
    if roles is not None:
        flag.roles = sorted(set(roles))
    if description is not None:
        flag.description = description
    flag.save()
    after = _flag_snapshot(flag)
    if before != after:
        audit.record(
            actor=actor,
            action="flag.changed",
            object_type="flag",
            object_id=flag.pk,
            before=before,
            after={"key": key, **after},
            reason=reason,
        )
    return flag


# --- protected settings (T-039) --------------------------------------------

SETTINGS = {
    "import.max_upload_mb": {
        "label": "Largest import file (MB)",
        "default": 20,
        "min": 1,
        "max": 200,
    },
    "retention.import_rows_days": {
        "label": "Days raw import rows are kept (D-015 pending)",
        "default": 365,
        "min": 30,
        "max": 3650,
    },
}


def get_setting(key):
    spec = SETTINGS[key]
    row = ProtectedSetting.objects.filter(key=key).first()
    return spec["default"] if row is None else row.value


def verify_step_up(user, *, password, code=""):
    """Re-authenticate before a protected change: the password, and the TOTP code if the user has
    an authenticator. Failures are audited."""
    from django_otp.plugins.otp_totp.models import TOTPDevice

    ok = bool(password) and user.check_password(password)
    device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if ok and device is not None:
        ok = bool(code) and device.verify_token(code)
    if not ok:
        audit.record(
            actor=user, action="auth.step_up_failed", object_type="user", object_id=user.pk
        )
        raise ConfigError("password", "Re-authentication failed. Check your password and code.")


def change_setting(*, actor, key, value, reason, password, code=""):
    if key not in SETTINGS:
        raise ConfigError("key", f"Unknown setting: {key}")
    if not reason.strip():
        raise ConfigError("reason", "State why the setting is being changed.")
    spec = SETTINGS[key]
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not spec["min"] <= value <= spec["max"]
    ):
        raise ConfigError("value", f"Enter a whole number from {spec['min']} to {spec['max']}.")
    verify_step_up(actor, password=password, code=code)
    before = get_setting(key)
    ProtectedSetting.objects.update_or_create(
        key=key, defaults={"value": value, "updated_by": actor, "updated_at": timezone.now()}
    )
    audit.record(
        actor=actor,
        action="setting.changed",
        object_type="setting",
        object_id=key,
        before={"value": before},
        after={"value": value},
        reason=reason.strip(),
    )


# --- lookups for other modules (the import pipeline) ------------------------


def _by_name(model, programme, text):
    """Sheets often carry a cohort or course NAME, not its code: accept an exact name match
    (case, spacing and punctuation ignored) when it is unambiguous."""
    hits = list(
        model.objects.filter(programme=programme, name_normalised=norm(text), active=True)[:2]
    )
    return hits[0] if len(hits) == 1 else None


def _find_course(prog, text):
    """A course by code, exact name, or a "<code>-<name>" label whose code and name both match."""
    from .models import Course

    hit = Course.objects.filter(programme=prog, code__iexact=text, active=True).first() or _by_name(
        Course, prog, text
    )
    if hit is None and (m := COURSE_LABEL.match(text.strip())):
        hit = Course.objects.filter(
            programme=prog,
            code__iexact=m.group(1),
            name_normalised=norm(m.group(2)),
            active=True,
        ).first()
    return hit


def resolve_offering(programme_code, cohort_code, course_code):
    """Find the active programme, cohort and course by code, and the offering joining cohort and
    course. Returns ``(offering_id, programme_id, institution_id, errors)`` where errors is a list
    of ``(field, message)``. Ids are strings (they go into JSON)."""
    from .models import Cohort, Programme

    errors, offering = [], None
    prog = cohort = course = None
    if programme_code:
        prog = Programme.objects.filter(code__iexact=programme_code, active=True).first()
        if prog is None:
            errors.append(("programme_code", f"Unknown programme '{programme_code}'."))
    if prog and cohort_code:
        cohort = Cohort.objects.filter(
            programme=prog, code__iexact=cohort_code, active=True
        ).first() or _by_name(Cohort, prog, cohort_code)
        if cohort is None:
            errors.append(("cohort_code", f"Unknown cohort '{cohort_code}' in this programme."))
    if prog and course_code:
        course = _find_course(prog, course_code)
        if course is None:
            errors.append(("course_code", f"Unknown course '{course_code}' in this programme."))
    if cohort and course:
        offering = cohort.offerings.filter(course=course).first()
        if offering is None:
            errors.append(("course_code", "This course is not offered in this cohort."))
    return (
        str(offering.pk) if offering else None,
        str(prog.pk) if prog else None,
        str(cohort.institution_id) if cohort else None,
        errors,
    )


# A cohort label such as "Gede VTC - 2021 Batch 1-Phase 1-Year 1" carries the training centre and
# the cohort identity (D-066 proposal; the pattern is one sheet's convention, extend as others
# appear). A course label is "<code>-<name>", e.g. "003-Carpentry".
COHORT_LABEL = re.compile(
    r"^(.+?)\s+-\s+(\d{4})\s+Batch\s+(\d+)\s*-\s*Phase\s+(\d+)\s*-\s*Year\s+(\d+)$", re.I
)
COURSE_LABEL = re.compile(r"^([A-Za-z0-9]+)\s*-\s*(.+)$")


def propose_reference(programme_code, cohort_text, course_text, county_id):
    """What would have to be created for this row's cohort/course to resolve? Returns a list of
    ``{"kind", "label", "data"}`` items (nothing is written), or None when the row cannot be
    resolved by creating records (unknown programme, label not in a known shape, or a new
    training centre with no usable county)."""
    from .models import Cohort, Programme, TrainingInstitution

    prog = Programme.objects.filter(code__iexact=programme_code, active=True).first()
    if prog is None:
        return None
    cohort_text, course_text = (cohort_text or "").strip(), (course_text or "").strip()
    cohort = Cohort.objects.filter(
        programme=prog, code__iexact=cohort_text, active=True
    ).first() or _by_name(Cohort, prog, cohort_text)
    course = _find_course(prog, course_text)
    if cohort and course and cohort.offerings.filter(course=course).exists():
        return None  # nothing missing
    items = []
    if cohort is None:
        m = COHORT_LABEL.match(cohort_text)
        if not m:
            return None
        inst_name, year, batch, phase, yos = m.groups()
        inst = TrainingInstitution.objects.filter(
            name_normalised=norm(inst_name), active=True
        ).first()
        if inst is None:
            if not county_id:
                return None
            items.append(
                {
                    "kind": "institutions",
                    "label": inst_name.strip(),
                    "data": {"name": inst_name.strip(), "county": county_id},
                }
            )
        items.append(
            {
                "kind": "cohorts",
                "label": cohort_text,
                "data": {
                    "name": cohort_text,
                    "programme": prog.code,
                    "institution": inst_name.strip(),
                    "intake_year": int(year),
                    "batch_no": int(batch),
                    "phase": int(phase),
                    "year_of_study": int(yos),
                },
            }
        )
    if course is None:
        m = COURSE_LABEL.match(course_text)
        if not m:
            return None
        items.append(
            {
                "kind": "courses",
                "label": course_text,
                "data": {
                    "code": m.group(1),
                    "name": m.group(2).strip(),
                    "programme": prog.code,
                },
            }
        )
    items.append(
        {
            "kind": "cohort-courses",
            "label": f"{cohort_text} / {course_text}",
            "data": {"cohort": cohort_text, "course": course_text, "programme": prog.code},
        }
    )
    return items


def _next_code(model, prefix, **scope):
    n = model.objects.filter(**scope, code__startswith=prefix).count() + 1
    while model.objects.filter(**scope, code=f"{prefix}{n:02d}").exists():
        n += 1
    return f"{prefix}{n:02d}"


@transaction.atomic
def create_proposed(*, actor, items):
    """Create the records a validated import proposed, each only if still missing (so it is safe
    to call twice). Order matters: centres, courses, cohorts, then the offerings joining them.
    Codes are generated here (centre ``I01``, cohort ``<centre>-21B1P1Y1``); CAP-YEI may rename
    them in Reference data. Returns the number of records created."""
    from .models import Cohort, CohortCourse, Course, Programme, TrainingInstitution

    order = {"institutions": 0, "courses": 1, "cohorts": 2, "cohort-courses": 3}
    made = 0
    for it in sorted(items, key=lambda i: order[i["kind"]]):
        d = it["data"]
        kind = it["kind"]
        prog = Programme.objects.get(code__iexact=d["programme"]) if "programme" in d else None
        if kind == "institutions":
            if TrainingInstitution.objects.filter(name_normalised=norm(d["name"])).exists():
                continue
            create_reference(
                actor=actor,
                key="institutions",
                data={
                    "name": d["name"],
                    "code": _next_code(TrainingInstitution, "I"),
                    "county": d["county"],
                    "kind": "vtc" if "vtc" in d["name"].lower() else "other",
                },
            )
        elif kind == "courses":
            if Course.objects.filter(programme=prog, code__iexact=d["code"]).exists():
                continue
            create_reference(
                actor=actor,
                key="courses",
                data={"code": d["code"], "name": d["name"], "programme": str(prog.pk)},
            )
        elif kind == "cohorts":
            if Cohort.objects.filter(programme=prog, name_normalised=norm(d["name"])).exists():
                continue
            inst = TrainingInstitution.objects.get(name_normalised=norm(d["institution"]))
            yy = f"{d['intake_year'] % 100:02d}"
            create_reference(
                actor=actor,
                key="cohorts",
                data={
                    "name": d["name"],
                    "code": f"{inst.code}-{yy}B{d['batch_no']}P{d['phase']}Y{d['year_of_study']}",
                    "programme": str(prog.pk),
                    "institution": str(inst.pk),
                    "intake_year": d["intake_year"],
                    "batch_no": d["batch_no"],
                    "phase": d["phase"],
                    "year_of_study": d["year_of_study"],
                },
            )
        else:
            cohort = (
                Cohort.objects.filter(programme=prog, active=True)
                .filter(name_normalised=norm(d["cohort"]))
                .first()
                or Cohort.objects.filter(programme=prog, code__iexact=d["cohort"]).first()
            )
            course = _find_course(prog, d["course"])
            if cohort is None or course is None:
                raise ConfigError("cohort_code", "A proposed record could not be matched.")
            if CohortCourse.objects.filter(cohort=cohort, course=course).exists():
                continue
            create_reference(
                actor=actor,
                key="cohort-courses",
                data={"cohort": str(cohort.pk), "course": str(course.pk)},
            )
        made += 1
    return made


def county_id_by_code(code):
    from .models import County

    row = County.objects.filter(code=code).first()
    if row is None:  # sheets usually say "Kisumu", not "42"
        hits = list(County.objects.filter(name_normalised=norm(code))[:2])
        row = hits[0] if len(hits) == 1 else None
    return str(row.pk) if row else None


def filter_options():
    """Programmes, cohorts and counties for filter drop-downs (names only, active first)."""
    from .models import Cohort, County, Programme, Sector

    def rows(qs, extra=()):
        return [
            {
                "id": str(o.pk),
                "code": o.code,
                "name": o.name,
                **{k: str(getattr(o, k)) for k in extra},
            }
            for o in qs
        ]

    cohorts = Cohort.objects.filter(active=True).select_related("institution")
    cohort_rows = rows(cohorts.order_by("-intake_year", "name"), extra=("programme_id",))
    institution = {str(c.pk): c.institution.name for c in cohorts}
    for r in cohort_rows:
        r["institution"] = institution[r["id"]]
    return {
        "programmes": rows(Programme.objects.filter(active=True).order_by("name")),
        "cohorts": cohort_rows,
        "counties": rows(County.objects.order_by("code")),
        "sectors": rows(Sector.objects.filter(active=True).order_by("name")),
    }


def normalise(text):
    """Public form of the name normaliser, for modules that match names (e.g. employers)."""
    return norm(text)


def reference_codes(limit=500):
    """Active programme, cohort and course codes for the import wizard's 'what do I type?' hint.
    Names only; no participant data."""
    from .models import Cohort, Course, Programme

    def rows(model):
        return [
            {"code": o.code, "name": o.name, "programme": o.programme.code}
            for o in model.objects.filter(active=True)
            .select_related("programme")
            .order_by("code")[:limit]
        ]

    return {
        "programme_code": [
            {"code": p.code, "name": p.name}
            for p in Programme.objects.filter(active=True).order_by("code")[:limit]
        ],
        "cohort_code": rows(Cohort),
        "course_code": rows(Course),
    }


def offering_ids(pk):
    """``(programme_id, institution_id)`` of an active course offering, or None if unknown."""
    from .models import CohortCourse

    row = (
        CohortCourse.objects.filter(pk=pk, active=True)
        .values_list("cohort__programme_id", "cohort__institution_id")
        .first()
    )
    return row


def county_exists(pk) -> bool:
    from .models import County

    return County.objects.filter(pk=pk).exists()


# --- referral reason codes (T-046, FR-18) ----------------------------------


def _reason_row(r):
    return {
        "id": str(r.pk), "code": r.code, "name": r.name, "applies_to": r.applies_to,
        "needs_note": r.needs_note, "active": r.active,
    }  # fmt: skip


def referral_reasons(stage=None, *, include_inactive=False):
    """Reason codes for an unsuccessful outcome; ``stage`` keeps those that apply to it."""
    from .models import ReferralReason

    qs = ReferralReason.objects.order_by("name")
    if not include_inactive:
        qs = qs.filter(active=True)
    if stage:
        qs = qs.filter(applies_to__in=[stage, ReferralReason.ANY])
    return [_reason_row(r) for r in qs]


def referral_reason(pk):
    """One reason code as a dict, or None if it does not exist."""
    from .models import ReferralReason

    try:
        return _reason_row(ReferralReason.objects.get(pk=pk))
    except (ReferralReason.DoesNotExist, ValueError, DjangoValidationError):
        return None


def active_reference(key, pk):
    """Active reference row of this kind and id, or None (unknown, retired or malformed)."""
    try:
        return kind_of(key).model.objects.filter(pk=pk, active=True).first()
    except (ValueError, DjangoValidationError):
        return None


def profile_options():
    """Active qualification levels, skills and sectors for the youth profile form."""
    from .models import QualificationLevel, Sector, Skill

    def rows(qs, *extra):
        return [
            {"id": str(o.pk), "code": o.code, "name": o.name, **{k: getattr(o, k) for k in extra}}
            for o in qs.filter(active=True)
        ]

    return {
        "levels": rows(QualificationLevel.objects.order_by("rank"), "rank"),
        "skills": rows(Skill.objects.order_by("category", "name"), "category"),
        "sectors": rows(Sector.objects.order_by("name")),
    }


def find_active_reference(key, text):
    """Active reference row whose code, else name, matches ``text``. Returns ``(row, problem)``;
    exactly one of them is None. Anything unclear is a problem, never a guess."""
    from .models import norm

    model = kind_of(key).model
    qs = model.objects.filter(active=True)
    hits = list(qs.filter(code__iexact=text.strip())[:2])
    if not hits:
        hits = list(qs.filter(name_normalised=norm(text))[:2])
    if not hits:
        return None, "no match"
    if len(hits) > 1:
        return None, "more than one match; use the code"
    return hits[0], None


def read_upload(name, data):
    """Rows of a CSV/Excel upload as ``[(row_number, cells)]`` (row 1 is the header).
    Raises ``ConfigError`` with field ``file`` when the file cannot be used."""
    from . import importer

    try:
        return importer.read_table(name, data)
    except importer.FileError as exc:
        raise ConfigError("file", str(exc)) from exc
