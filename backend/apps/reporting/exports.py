# ruff: noqa: E501
"""De-identified exports (T-071, RPT-04, SEC-15).

What makes an export de-identified here, in order of strength:

1. Direct identifiers never enter it: no name, phone, email, ID number, address or free text.
   Only the columns listed in ``FIELDS`` can appear, and a test fails if one is added by accident.
2. Each youth gets a random reference made for that one export and kept nowhere, so two exports
   cannot be joined and the reference cannot be traced back to a record.
3. Detail is reduced: age is a band, location is a county, and rows come out in random order.
4. Small groups are hidden. A youth whose gender, age band and county are shared with fewer than
   the threshold others has the county, then the age band, replaced by "Not shown"; if the group
   is still too small the youth is left out and counted as withheld. In summaries, a count below
   the threshold shows as "< threshold", and a second cell is hidden when one hidden cell could
   be worked out from a total.
5. The file is kept for a limited time, then deleted. Every export, download and deletion is
   written to the log and to the audit trail.

The threshold and the expiry are working defaults until CAP-YEI decides D-045; both are on the
Rules settings page."""

import csv
import io
import secrets
from collections import Counter
from datetime import date, timedelta
from random import SystemRandom

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.participants import services as participants
from apps.referrals import services as referrals

from . import services as reporting
from .models import ExportLog

NOT_SHOWN = "Not shown"
FORMATS = ("csv", "xlsx")
GENDER = dict(reporting.GENDERS)
BAND = {k: label for k, label, _lo, _hi in reporting.AGE_BANDS} | {"unknown": "Age not recorded"}
STATUS = {"active": "Active", "archived": "Archived"}

# The only columns any export may contain: (key, heading, meaning).
FIELDS = {
    "youth_records": [
        ("reference", "Reference", "Random code made for this export only. It cannot be matched to a record or to another export."),
        ("gender", "Gender", "As recorded: Female, Male, Other or Not recorded."),
        ("age_band", "Age band", "Age today in the band shown, never the date of birth."),
        ("county", "County", "County the youth comes from. Not the ward, village or address."),
        ("referred", "Referred", "Yes if the youth has at least one submitted referral."),
        ("placed", "Placed", "Yes if the youth has a placement recorded as placed, or a referral that reached Placed."),
    ],
    "summary": [
        ("dimension", "Grouped by", "The way the youth are grouped on this row."),
        ("group", "Group", "The gender, age band or county."),
        ("registered", "Registered youth", "Youth records in the group."),
        ("referred", "Referred", "Youth in the group with at least one submitted referral."),
        ("placed", "Placed", "Youth in the group recorded as placed."),
    ],
}  # fmt: skip
DATASETS = {
    "youth_records": "One row per youth with a random reference, gender, age band, county and whether referred or placed.",
    "summary": "Counts of registered, referred and placed youth by gender, age band and county.",
}
CELL = ("registered", "referred", "placed")


class ExportError(Exception):
    def __init__(self, field, message, code):
        super().__init__(message)
        self.field, self.message, self.code = field, message, code


def _numbers():
    from apps.intelligence import services as intelligence

    return intelligence.setting("exports.small_cell"), intelligence.setting("exports.expiry_days")


def _youth(user, today):
    """The people the user may see, with the fields an export may use. No names are read."""
    facts = participants.report_facts(user)
    ids = {y["id"] for y in facts}
    refs = referrals.report_facts(user)
    referred, placed, _ = reporting.outcomes(user, ids, refs)
    out = []
    for y in facts:
        out.append(
            {
                "gender": GENDER.get(y["gender"], GENDER["unknown"]),
                "age_band": BAND[reporting._band(reporting._age(y, today))],
                "county": y["county"] or "County not recorded",
                "referred": y["id"] in referred,
                "placed": y["id"] in placed,
            }
        )  # fmt: skip
    return out


def _generalise(people, threshold):
    """Make every kept youth share gender, age band and county with at least ``threshold - 1``
    others. Returns ``(kept, withheld count)``."""

    def sizes(keys):
        return Counter(tuple(p[k] for k in keys) for p in people)

    for keys, hide in ((("gender", "age_band", "county"), "county"), (("gender", "age_band"), "age_band")):  # fmt: skip
        small = {k for k, n in sizes(keys).items() if n < threshold}
        for p in people:
            if tuple(p[k] for k in keys) in small:
                p[hide] = NOT_SHOWN
                if hide == "age_band":
                    p["county"] = NOT_SHOWN
    keys = ("gender", "age_band", "county")
    final = sizes(keys)
    kept = [p for p in people if final[tuple(p[k] for k in keys)] >= threshold]
    return kept, len(people) - len(kept)


def _records(user, today, threshold):
    people = _youth(user, today)
    kept, withheld = _generalise(people, threshold)
    rng = SystemRandom()
    rng.shuffle(kept)
    seen: set = set()
    rows = []
    for p in kept:
        while (ref := "Y-" + secrets.token_hex(4).upper()) in seen:
            pass
        seen.add(ref)
        rows.append(
            {
                "reference": ref,
                "gender": p["gender"],
                "age_band": p["age_band"],
                "county": p["county"],
                "referred": "Yes" if p["referred"] else "No",
                "placed": "Yes" if p["placed"] else "No",
            }
        )  # fmt: skip
    return rows, withheld, 0


def _summary(user, today, threshold):
    people = _youth(user, today)
    rows, hidden = [], 0
    for dimension, key in (("Gender", "gender"), ("Age band", "age_band"), ("County", "county")):
        groups: dict = {}
        for p in people:
            g = groups.setdefault(p[key], dict.fromkeys(CELL, 0))
            g["registered"] += 1
            g["referred"] += p["referred"]
            g["placed"] += p["placed"]
        block = [
            {"dimension": dimension, "group": name, **vals} for name, vals in sorted(groups.items())
        ]
        for col in CELL:
            small = [r for r in block if 0 < r[col] < threshold]
            if not small:
                continue
            extra = []
            if len(small) == 1:
                # One hidden cell could be worked out from the total, so hide the next smallest too.
                rest = sorted((r for r in block if r[col] >= threshold), key=lambda r: r[col])
                extra = rest[:1]
            for r in small:
                r[col] = f"< {threshold}"
            for r in extra:
                r[col] = "Hidden"
            hidden += len(small) + len(extra)
        rows.extend(block)
    return rows, 0, hidden


BUILDERS = {"youth_records": _records, "summary": _summary}


def _clean(v):
    """Stop a spreadsheet reading a cell as a formula."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v


def _csv(dataset, rows) -> bytes:
    keys = [k for k, *_ in FIELDS[dataset]]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([h for _k, h, _m in FIELDS[dataset]])
    for r in rows:
        w.writerow([_clean(r[k]) for k in keys])
    return buf.getvalue().encode("utf-8-sig")


def _xlsx(dataset, rows, *, threshold, expires, created, withheld, hidden) -> bytes:
    from openpyxl import Workbook

    keys = [k for k, *_ in FIELDS[dataset]]
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append([h for _k, h, _m in FIELDS[dataset]])
    for r in rows:
        ws.append([_clean(r[k]) for k in keys])
    d = wb.create_sheet("Definitions")
    d.append(["Column", "Meaning"])
    for _k, h, m in FIELDS[dataset]:
        d.append([h, m])
    d.append([])
    d.append(["Made", f"{created:%Y-%m-%d %H:%M}"])
    d.append(["Delete by", f"{expires:%Y-%m-%d}"])
    d.append(["Smallest group shown", threshold])
    d.append(["Youth left out as too few to show", withheld])
    d.append(["Counts hidden", hidden])
    d.append(["Handling", "De-identified. Do not try to identify anyone, join this to other data or share it beyond the purpose it was made for."])  # fmt: skip
    d.append(["Status", "The threshold and the definitions are working values until CAP-YEI approves them (D-045, RPT-04)."])  # fmt: skip
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def serialize(log: ExportLog) -> dict:
    now = timezone.now()
    return {
        "id": str(log.id),
        "dataset": log.dataset,
        "format": log.file_format,
        "filename": log.filename,
        "rows": log.row_count,
        "withheld_rows": log.withheld_rows,
        "suppressed_cells": log.suppressed_cells,
        "threshold": log.small_cell_threshold,
        "downloads": log.downloads,
        "created_at": log.created_at,
        "expires_at": log.expires_at,
        "available": log.content is not None and log.expires_at > now,
        "expired": log.expires_at <= now or log.purged_at is not None,
        "by": log.actor_label,
    }


def overview(user) -> dict:
    threshold, expiry = _numbers()
    mine = ExportLog.objects.filter(actor=user, dataset__in=list(BUILDERS))[:50]
    return {
        "datasets": [
            {
                "key": k,
                "description": d,
                "columns": [{"heading": h, "meaning": m} for _k, h, m in FIELDS[k]],
            }
            for k, d in DATASETS.items()
        ],
        "formats": list(FORMATS),
        "rules": {"small_cell": threshold, "expiry_days": expiry},
        "log": [serialize(x) for x in mine],
    }


def create(*, actor, dataset, file_format, now=None) -> ExportLog:
    if dataset not in BUILDERS:
        raise ExportError("dataset", "Choose one of the listed datasets.", "invalid")
    if file_format not in FORMATS:
        raise ExportError("format", "Choose CSV or Excel.", "invalid")
    now = now or timezone.now()
    today = timezone.localdate(now) if timezone.is_aware(now) else date.today()
    threshold, expiry = _numbers()
    rows, withheld, hidden = BUILDERS[dataset](actor, today, threshold)
    expires = now + timedelta(days=expiry)
    if file_format == "csv":
        content = _csv(dataset, rows)
    else:
        content = _xlsx(
            dataset, rows, threshold=threshold, expires=expires, created=now,
            withheld=withheld, hidden=hidden,
        )  # fmt: skip
    name = f"pi360-deidentified-{dataset.replace('_', '-')}-{today:%Y%m%d}.{file_format}"
    with transaction.atomic():
        log = ExportLog.objects.create(
            actor=actor, actor_label=actor.get_username()[:150], dataset=dataset,
            file_format=file_format, filename=name, row_count=len(rows), withheld_rows=withheld,
            suppressed_cells=hidden, small_cell_threshold=threshold, content=content,
            expires_at=expires,
        )  # fmt: skip
        audit.record(
            actor=actor, action="export.created", object_type="export", object_id=log.id,
            after={
                "dataset": dataset, "format": file_format, "rows": len(rows),
                "withheld_rows": withheld, "suppressed_cells": hidden, "threshold": threshold,
                "expires_at": expires.isoformat(),
            },
        )  # fmt: skip
    return log


def download(*, actor, export_id) -> tuple[ExportLog, bytes]:
    """The file, only for the person who made it and only before it expires."""
    log = ExportLog.objects.filter(pk=export_id, actor=actor, dataset__in=list(BUILDERS)).first()
    if log is None:
        raise ExportError("id", "There is no such export.", "not_found")
    if log.content is None or log.expires_at <= timezone.now():
        raise ExportError("id", "This export has expired. Make a new one.", "expired")
    with transaction.atomic():
        ExportLog.objects.filter(pk=log.pk).update(downloads=log.downloads + 1)
        audit.record(
            actor=actor, action="export.downloaded", object_type="export", object_id=log.id,
            after={"dataset": log.dataset, "format": log.file_format},
        )  # fmt: skip
    return log, bytes(log.content)


def purge_expired(*, now=None) -> int:
    """Delete the files of expired exports. The log row stays. Returns how many were cleared."""
    now = now or timezone.now()
    due = ExportLog.objects.filter(expires_at__lte=now, content__isnull=False)
    ids = list(due.values_list("pk", flat=True))
    if not ids:
        return 0
    with transaction.atomic():
        ExportLog.objects.filter(pk__in=ids).update(content=None, purged_at=now)
        audit.record(
            actor=None, action="export.purged", object_type="export", object_id="expired",
            after={"files_deleted": len(ids)},
        )  # fmt: skip
    return len(ids)


# --- Table exports (identifiable): the list on screen, as filtered, with names ---------------------
# The file holds what the table shows and is sent straight back; it is never stored. Each one needs
# the grant-only permission ``exports.identifiable`` and a stated purpose, and is logged and audited.

TABLES = {
    "youth": {
        "label": "Youth",
        "slug": "youth",
        "columns": [
            ("name", "Name"),
            ("gender", "Gender"),
            ("age", "Age"),
            ("programme", "Programme"),
            ("cohort", "Cohort"),
            ("county", "County"),
            ("status", "Status"),
        ],
        "rows": lambda user, params: participants.directory_rows(user, params),
    },
}
FILTER_KEYS = ("q", "programme", "cohort", "county", "status", "archived")
TABLE_CONTENT = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _table_file(table, rows, file_format, about) -> bytes:
    keys = [k for k, _h in table["columns"]]
    heads = [h for _k, h in table["columns"]]
    if file_format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(heads)
        for r in rows:
            w.writerow([_clean(r[k]) for k in keys])
        return buf.getvalue().encode("utf-8-sig")
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(heads)
    for r in rows:
        ws.append([_clean(r[k]) for k in keys])
    a = wb.create_sheet("About")
    a.append(["Item", "Value"])
    for k, v in about:
        a.append([k, v])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def export_table(*, actor, dataset, params, file_format, purpose, now=None):
    """``(log, file bytes, file name)`` for the rows the caller sees under ``params``."""
    table = TABLES.get(dataset)
    if table is None:
        raise ExportError("dataset", "There is no such table to export.", "not_found")
    if file_format not in FORMATS:
        raise ExportError("format", "Choose CSV or Excel.", "invalid")
    purpose = (purpose or "").strip()
    if not purpose:
        raise ExportError("purpose", "State what the file is for.", "required")
    now = now or timezone.now()
    try:
        rows = table["rows"](actor, params)
    except participants.FilterError as exc:
        raise ExportError("filter", str(exc), "invalid") from None
    if not rows:
        raise ExportError(
            "filter", "No rows match these filters, so there is nothing to export.", "empty"
        )
    used = {k: params.get(k) for k in FILTER_KEYS if params.get(k)}
    about = [
        ("Table", table["label"]),
        ("Made", f"{now:%Y-%m-%d %H:%M}"),
        ("Made by", actor.get_username()),
        ("Rows", len(rows)),
        ("Filters", ", ".join(f"{k}={v}" for k, v in used.items()) or "none"),
        ("Purpose", purpose),
        ("Handling", "Contains names. Use only for the purpose stated, keep it secure, and delete it when done."),
    ]  # fmt: skip
    content = _table_file(table, rows, file_format, about)
    name = f"pi360-{table['slug']}-{timezone.localdate(now):%Y%m%d}.{file_format}"
    with transaction.atomic():
        log = ExportLog.objects.create(
            actor=actor, actor_label=actor.get_username()[:150], dataset=dataset,
            file_format=file_format, filename=name, row_count=len(rows),
            detail={"filters": used, "purpose": purpose, "columns": [h for _k, h in table["columns"]]},
        )  # fmt: skip
        audit.record(
            actor=actor, action="export.created", object_type="export", object_id=log.id,
            after={
                "dataset": dataset, "format": file_format, "rows": len(rows), "filters": used,
                "identifiable": True,
            },
            reason=purpose,
        )  # fmt: skip
    return log, content, name
