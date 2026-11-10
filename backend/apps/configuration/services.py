"""Public interface of apps.configuration: reference data, feature flags, protected settings.
Other modules import only this module. Every change is audited in the same transaction."""

import uuid

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
