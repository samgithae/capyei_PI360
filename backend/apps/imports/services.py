"""Import pipeline (T-040): template -> upload (dry run) -> approve -> chunked commit -> rollback.

Upload only reads and validates: it writes batch/row records and nothing else. Participant data
changes only in ``commit``, in chunks, each its own transaction (ADR-020).
"""

import csv
import hashlib
import io
import json

from django.db import transaction
from django.utils import timezone

from apps.api import runtime
from apps.audit import services as audit
from apps.employers import services as employers
from apps.participants import services as participants
from apps.placements import services as placements

from . import placement_rows
from .models import (
    ImportBatch,
    ImportRow,
    MappingTemplate,
    ReconciliationSignoff,
    RecordLineage,
)
from .parsing import FileError, read_rows

CHUNK_SIZE = 500
LOADED = (ImportBatch.COMMITTED, ImportBatch.PARTIAL)


class ImportFailure(Exception):
    def __init__(self, message, field="file"):
        super().__init__(message)
        self.message, self.field = message, field


# --- templates -------------------------------------------------------------


# D-059 (working decision): imports add new people only. Flip to allow updates once CAP-YEI
# names the fields an import may change.
ALLOW_UPDATES = False

# Fields a file may leave out of the mapping if the user sets them once for the whole file
# (doc 15 §3 step 4). A default fills only empty cells, never a value in the file.
DEFAULTABLE = ("programme_code", "cohort_code", "course_code")


TARGETS = ("participants", "placements")


def _fields(target):
    return placement_rows.FIELDS if target == "placements" else participants.FIELDS


def _is_target(target, name):
    return (placement_rows if target == "placements" else participants).is_target(name)


def _defaultable(target):
    return placement_rows.DEFAULTABLE if target == "placements" else DEFAULTABLE


def _check_row(target, mapped):
    return (placement_rows if target == "placements" else participants).check_row(mapped)


def create_template(*, actor, source, columns, target="participants") -> MappingTemplate:
    if target not in TARGETS:
        raise ImportFailure(f"Unknown target '{target}'.", "target")
    if not isinstance(columns, dict) or not columns:
        raise ImportFailure("Give a mapping of source column to field.", "columns")
    unknown = sorted(t for t in set(columns.values()) if not _is_target(target, t))
    if unknown:
        raise ImportFailure(f"Unknown target field(s): {', '.join(unknown)}.", "columns")
    missing = [
        f
        for f, req in _fields(target).items()
        if req and f not in columns.values() and f not in _defaultable(target)
    ]
    if missing:
        raise ImportFailure(f"Required field(s) not mapped: {', '.join(missing)}.", "columns")
    with transaction.atomic():
        last = (
            MappingTemplate.objects.select_for_update()
            .filter(source=source)
            .order_by("-version")
            .first()
        )
        t = MappingTemplate.objects.create(
            source=source,
            version=(last.version + 1) if last else 1,
            target=target,
            columns=columns,
            created_by=actor,
        )
        audit.record(
            actor=actor,
            action="import.template_created",
            object_type="mapping_template",
            object_id=t.pk,
            after={"source": source, "version": t.version},
        )
    return t


# --- inspect (T-059) --------------------------------------------------------

# Extra header spellings seen in source files (doc 15 §3 step 3). Proposals pending D-050/D-062.
SYNONYMS = {
    "name": "full_name", "fullname": "full_name", "traineename": "full_name",
    "trainee": "full_name", "traineecontact": "phone",
    "programme": "programme_code", "program": "programme_code", "prog": "programme_code",
    "cohort": "cohort_code", "course": "course_code", "enrollmentnumber": "enrollment_no",
    "enrolmentno": "enrollment_no", "enrolno": "enrollment_no", "enrollmentno": "enrollment_no",
    "sex": "gender", "county": "county_code", "countycode": "county_code",
    "phonenumber": "phone", "mobile": "phone", "telephone": "phone", "emailaddress": "email",
    "id": "source_id", "sourceid": "source_id",
}  # fmt: skip


def _norm(h: str) -> str:
    return "".join(c for c in h.lower() if c.isalnum())


def inspect(*, file_name, data: bytes, target="participants") -> dict:
    """Read a file's shape without storing anything: headers, row count, empty columns, a
    suggested column mapping and any saved template whose columns are all present. The wizard
    uses this before a mapping exists (doc 15 §3 steps 2-3)."""
    limit_mb = runtime.setting("import.max_upload_mb", 20)
    if len(data) > limit_mb * 1024 * 1024:
        raise ImportFailure(f"The file is larger than {limit_mb} MB.")
    try:
        headers, rows = read_rows(file_name, data)
    except FileError as exc:
        raise ImportFailure(str(exc)) from exc
    headers = [h for h in headers if h]
    fields = _fields(target)
    by_norm = {_norm(f): f for f in fields} | (
        placement_rows.SYNONYMS if target == "placements" else SYNONYMS
    )
    taken: set[str] = set()
    suggested: dict[str, str] = {}
    for h in headers:
        field = by_norm.get(_norm(h))
        if field and field not in taken:
            suggested[h] = field
            taken.add(field)
        elif (
            target == "participants"
            and len(h) <= participants.MAX_EXTRA_LABEL
            and any(r.get(h) for r in rows)
        ):
            # Nothing is dropped by default: an unrecognised column with data is kept as extra.
            suggested[h] = participants.EXTRA + h
    fits = [
        t for t in MappingTemplate.objects.filter(active=True, target=target)
        .order_by("source", "-version")
        if all(c in headers for c in t.columns)
    ]  # fmt: skip
    return {
        "headers": headers,
        "row_count": len(rows),
        "empty_columns": [h for h in headers if not any(r.get(h) for r in rows)],
        "suggested": suggested,
        "fields": [{"field": f, "required": req} for f, req in fields.items()],
        "target": target,
        "defaultable": list(_defaultable(target)),
        "matching_templates": [str(t.pk) for t in fits],
        # The first data row as {header: text}, so people can see what each column holds.
        "sample": {h: str(rows[0].get(h) or "")[:80] for h in headers} if rows else {},
        "reference_codes": participants.reference_codes(),
        "already_loaded": ImportBatch.objects.filter(
            file_hash=hashlib.sha256(data).hexdigest(), status__in=LOADED
        ).exists(),
    }


# --- upload / dry run ------------------------------------------------------


def _row_hash(raw: dict) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()


def upload(*, actor, template, file_name, data: bytes, defaults=None) -> ImportBatch:
    """Parse and validate. Changes no participant data (the dry run). ``defaults`` sets
    programme, cohort and course once for the file; they fill empty cells only."""
    defaults = {k: str(v).strip() for k, v in (defaults or {}).items() if str(v).strip()}
    target = template.target
    bad = sorted(set(defaults) - set(_defaultable(target)))
    if bad:
        raise ImportFailure(f"Cannot set a default for: {', '.join(bad)}.", "defaults")
    unset = [
        f for f in _defaultable(target) if f not in template.columns.values() and f not in defaults
    ]
    if unset:
        raise ImportFailure(
            f"{', '.join(unset)}: not mapped from a column and no default given.", "defaults"
        )
    limit_mb = runtime.setting("import.max_upload_mb", 20)
    if len(data) > limit_mb * 1024 * 1024:
        raise ImportFailure(f"The file is larger than {limit_mb} MB.")
    try:
        headers, rows = read_rows(file_name, data)
    except FileError as exc:
        raise ImportFailure(str(exc)) from exc
    missing = [c for c in template.columns if c not in headers]
    if missing:
        raise ImportFailure(f"Column(s) missing from the file: {', '.join(missing)}.")

    file_hash = hashlib.sha256(data).hexdigest()
    same = ImportBatch.objects.filter(file_hash=file_hash, status__in=LOADED).first()
    seen_keys: dict[str, int] = {}
    plan: dict[tuple, dict] = {}
    counts = {"total": len(rows), "create": 0, "update": 0, "held": 0, "skip": 0, "warnings": 0}
    with transaction.atomic():
        batch = ImportBatch.objects.create(
            template=template,
            file_name=file_name[:255],
            file_hash=file_hash,
            defaults=defaults,
            uploaded_by=actor,
            duplicate_of=same,
        )
        objs = []
        for n, raw in enumerate(rows, start=1):
            mapped = {template.columns[h]: raw.get(h, "") for h in template.columns}
            for f, value in defaults.items():
                if not str(mapped.get(f, "") or "").strip():
                    mapped[f] = value
            checked = _check_row(target, mapped)
            rh = _row_hash(raw)
            outcome = ImportRow.UPDATE if checked.match == "exact" else ImportRow.CREATE
            errors = list(checked.errors)
            if checked.source_key and target == "participants":
                if checked.source_key in seen_keys:
                    first = seen_keys[checked.source_key]
                    errors.append(
                        {
                            "field": "enrollment_no",
                            "message": f"Same enrollment number as row {first}.",
                        }
                    )
                else:
                    seen_keys[checked.source_key] = n
            if errors:
                outcome = ImportRow.HELD
            elif checked.match == "exact" and not ALLOW_UPDATES:
                outcome = ImportRow.SKIP
                checked.warnings.append(
                    {"field": "", "message": "Already in PI360; imports add new people only."}
                )
            elif checked.clean.get("_skip"):
                outcome = ImportRow.SKIP
            elif _already_loaded(template.source, checked.source_key, rh):
                outcome = ImportRow.SKIP
                checked.warnings.append({"field": "", "message": "Already loaded; skipped."})
            if outcome in (ImportRow.CREATE, ImportRow.UPDATE):
                for item in checked.clean.get("_proposed", []):
                    plan.setdefault((item["kind"], item["label"]), item)
            counts[outcome] += 1
            counts["warnings"] += bool(checked.warnings)
            objs.append(
                ImportRow(
                    batch=batch,
                    row_no=n,
                    row_hash=rh,
                    source_key=checked.source_key,
                    raw=raw,
                    clean=checked.clean,
                    match=checked.match,
                    outcome=outcome,
                    errors=errors,
                    warnings=checked.warnings,
                    diff=checked.diff,
                )
            )
        ImportRow.objects.bulk_create(objs, batch_size=1000)
        batch.counts = counts
        batch.reference_plan = list(plan.values())
        batch.status = ImportBatch.VALIDATED
        batch.save()
        audit.record(
            actor=actor,
            action="import.uploaded",
            object_type="import_batch",
            object_id=batch.pk,
            after={"file_hash": file_hash, "counts": counts, "template": str(template)},
        )
    return batch


def _already_loaded(source, source_key, row_hash) -> bool:
    return ImportRow.objects.filter(
        committed=True,
        row_hash=row_hash,
        source_key=source_key,
        batch__template__source=source,
        batch__status__in=LOADED,
    ).exists()


# --- approve / commit ------------------------------------------------------


def approve(*, actor, batch, create_reference=False):
    """Approve a validated batch. If the file implies new centres, cohorts or courses
    (``reference_plan``), the approver must confirm them with ``create_reference``; they are
    created here, then every row that depended on them is re-checked."""
    if batch.status != ImportBatch.VALIDATED:
        raise ImportFailure("Only a validated batch can be approved.", "status")
    if batch.reference_plan and not create_reference:
        raise ImportFailure(
            f"This file needs {len(batch.reference_plan)} new reference record(s) "
            "(training centres, cohorts or courses). Confirm them to approve.",
            "create_reference",
        )
    with transaction.atomic():
        if batch.reference_plan:
            try:
                made = participants.create_proposed_reference(
                    actor=actor, items=batch.reference_plan
                )
            except ValueError as exc:
                raise ImportFailure(str(exc), "create_reference") from exc
            blocked = 0
            for row in batch.rows.filter(outcome__in=[ImportRow.CREATE, ImportRow.UPDATE]):
                if "_proposed" not in row.clean:
                    continue
                problems = participants.offering_resolves(row.clean)
                if problems:
                    row.outcome = ImportRow.HELD
                    row.errors = [{"field": f, "message": m} for f, m in problems]
                    row.save(update_fields=["outcome", "errors"])
                    batch.counts["held"] += 1
                    batch.counts["create"] -= 1
                    blocked += 1
            audit.record(
                actor=actor,
                action="import.reference_created",
                object_type="import_batch",
                object_id=batch.pk,
                after={"records": made, "plan": len(batch.reference_plan), "blocked": blocked},
            )
        batch.status, batch.approved_by = ImportBatch.APPROVED, actor
        batch.save()
        audit.record(
            actor=actor, action="import.approved", object_type="import_batch", object_id=batch.pk
        )


def cancel(*, actor, batch):
    if batch.status not in (ImportBatch.UPLOADED, ImportBatch.VALIDATED, ImportBatch.APPROVED):
        raise ImportFailure("This batch can no longer be cancelled.", "status")
    batch.status = ImportBatch.CANCELLED
    batch.save()
    audit.record(
        actor=actor, action="import.cancelled", object_type="import_batch", object_id=batch.pk
    )


def commit(*, actor, batch) -> ImportBatch:
    """Commit approved rows in chunks. Safe to call again: committed rows are skipped, so a
    repeat does nothing and a partial batch resumes from the first uncommitted row."""
    if batch.status == ImportBatch.COMMITTED:
        return batch
    if batch.status not in (ImportBatch.APPROVED, ImportBatch.PARTIAL, ImportBatch.COMMITTING):
        raise ImportFailure("Approve the batch before committing it.", "status")
    batch.status = ImportBatch.COMMITTING
    batch.save()
    todo = batch.rows.filter(
        committed=False, outcome__in=[ImportRow.CREATE, ImportRow.UPDATE]
    ).order_by("row_no")
    try:
        while True:
            chunk = list(todo[:CHUNK_SIZE])
            if not chunk:
                break
            with transaction.atomic():
                for row in chunk:
                    if batch.template.target == "placements":
                        pid, before, after = placement_rows.commit_row(
                            row.clean, actor=actor, row_id=row.pk
                        )
                        action = "create"
                    else:
                        action, pid, before, after = participants.import_participant(
                            row.clean, batch_ref=str(batch.pk)
                        )
                    RecordLineage.objects.create(
                        row=row,
                        entity="placement"
                        if batch.template.target == "placements"
                        else "participant",
                        record_id=pid,
                        action=action,
                        before=before,
                        after=after,
                    )
                    row.committed, row.record_id = True, pid
                    row.save(update_fields=["committed", "record_id"])
    except Exception:
        batch.status = ImportBatch.PARTIAL
        batch.save()
        audit.record(
            actor=actor,
            action="import.commit_failed",
            object_type="import_batch",
            object_id=batch.pk,
            after={"committed_rows": batch.rows.filter(committed=True).count()},
        )
        raise
    batch.status, batch.committed_at = ImportBatch.COMMITTED, timezone.now()
    batch.save()
    audit.record(
        actor=actor,
        action="import.committed",
        object_type="import_batch",
        object_id=batch.pk,
        after=batch.counts,
    )
    # Quarantine (T-041): queue possible duplicates among the new records for a steward.
    if batch.template.target == "participants":
        created = RecordLineage.objects.filter(row__batch=batch, action="create").values_list(
            "record_id", flat=True
        )
        participants.scan(only=list(created))
    return batch


# --- rollback --------------------------------------------------------------


def rollback(*, actor, batch, reason):
    """Undo a committed batch while no later batch touched the same records."""
    if batch.status not in LOADED:
        raise ImportFailure("Only a committed batch can be rolled back.", "status")
    if not reason.strip():
        raise ImportFailure("Give a reason.", "reason")
    if ReconciliationSignoff.objects.filter(batch=batch).exists():
        raise ImportFailure("This batch is signed off, so it cannot be rolled back.", "status")
    mine = RecordLineage.objects.filter(row__batch=batch, reverted=False).order_by("-pk")
    is_placements = batch.template.target == "placements"
    if not is_placements and participants.involved_in_merge(
        mine.values_list("record_id", flat=True)
    ):
        raise ImportFailure(
            "Some of these records were merged by a steward. Undo those merges first.", "status"
        )
    first_pk = (
        RecordLineage.objects.filter(row__batch=batch)
        .order_by("pk")
        .values_list("pk", flat=True)
        .first()
    )
    if (
        first_pk is not None
        and RecordLineage.objects.filter(
            record_id__in=mine.values("record_id"), reverted=False, pk__gt=first_pk
        )
        .exclude(row__batch=batch)
        .exists()
    ):
        raise ImportFailure(
            "Later imports changed some of these records. Fix them by correction instead.",
            "status",
        )
    with transaction.atomic():
        if is_placements:
            try:
                placement_rows.undo_rows(actor=actor, entries=list(mine))
                employers.reverse_source(actor=actor, source=str(batch.pk))
            except ValueError as exc:  # PlacementError and ClusterError are both ValueErrors
                raise ImportFailure(str(exc), "status") from exc
            mine.update(reverted=True)
        else:
            for entry in mine:
                participants.undo_import(
                    action=entry.action, participant_id=entry.record_id, before=entry.before
                )
                entry.reverted = True
                entry.save(update_fields=["reverted"])
        batch.rows.update(committed=False)
        batch.status = ImportBatch.ROLLED_BACK
        batch.save()
        audit.record(
            actor=actor,
            action="import.rolled_back",
            object_type="import_batch",
            object_id=batch.pk,
            reason=reason,
        )


# --- reports ---------------------------------------------------------------


def _safe(v) -> str:
    """Stop spreadsheet formula injection: cells that begin with = + - @ are prefixed."""
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def error_report(batch) -> str:
    """CSV of every held row and warning, for correction at source. Carries row numbers and
    messages only, never the row's own values."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["row", "severity", "field", "message"])
    for row in batch.rows.exclude(errors=[], warnings=[]).order_by("row_no"):
        for e in row.errors:
            w.writerow([row.row_no, "error", e["field"], _safe(e["message"])])
        for e in row.warnings:
            w.writerow([row.row_no, "warning", e["field"], _safe(e["message"])])
    return out.getvalue()


# --- reconciliation and contract (T-042) ----------------------------------------------------


def reconciliation(batch) -> dict:
    """Prove every source row is accounted for: each lands in exactly one bucket, so the buckets
    add up to the file's row count. Also compares per-cohort control totals with what PI360 now
    holds, and lists held rows with their reasons (never their values)."""
    lineage = RecordLineage.objects.filter(row__batch=batch)
    created = lineage.filter(action="create", reverted=False).count()
    updated = lineage.filter(action="update", reverted=False).count()
    rolled_back = lineage.filter(reverted=True).count()
    bare = batch.rows.filter(lineage__isnull=True)
    held = bare.filter(outcome=ImportRow.HELD).count()
    skipped = bare.filter(outcome=ImportRow.SKIP).count()
    pending = bare.filter(outcome__in=[ImportRow.CREATE, ImportRow.UPDATE]).count()
    total = batch.rows.count()
    buckets = {
        "created": created, "updated": updated, "skipped": skipped, "held": held,
        "pending": pending, "rolled_back": rolled_back,
    }  # fmt: skip

    live = list(lineage.filter(reverted=False).values_list("row__clean", "record_id"))
    if batch.template.target == "placements":
        live = []  # per-cohort control totals describe people, not placements
    by_cohort: dict[str, set] = {}
    for clean, rid in live:
        by_cohort.setdefault(str(clean.get("cohort_code", "")).upper(), set()).add(rid)
    held_in_db = participants.cohort_counts({r for _, r in live})
    controls = [
        {"cohort": code, "source": len(ids), "pi360": held_in_db.get(code, 0),
         "matches": len(ids) == held_in_db.get(code, 0)}
        for code, ids in sorted(by_cohort.items())
    ]  # fmt: skip

    quarantined = (
        []
        if batch.template.target == "placements"
        else participants.quarantined(
            lineage.filter(action="create", reverted=False).values_list("record_id", flat=True)
        )
    )
    held_rows = [
        {"row": r.row_no, "reasons": [f"{e['field']}: {e['message']}" for e in r.errors]}
        for r in batch.rows.filter(outcome=ImportRow.HELD).order_by("row_no")[:500]
    ]
    return {
        "batch": str(batch.pk),
        "status": batch.status,
        "source_rows": total,
        **buckets,
        "accounted_for": sum(buckets.values()),
        "balanced": total == sum(buckets.values()),
        "quarantined": len(quarantined),
        "controls": controls,
        "controls_match": all(c["matches"] for c in controls),
        "held_rows": held_rows,
    }


def sign_off(*, actor, batch, signer_name, signer_role, signed_on, note=""):
    """Record the data owner's sign-off. Only a loaded batch whose buckets balance and whose
    cohort control totals match can be signed; a signed batch cannot be rolled back."""
    if batch.status not in LOADED:
        raise ImportFailure("Only a loaded batch can be signed off.", "status")
    if ReconciliationSignoff.objects.filter(batch=batch).exists():
        raise ImportFailure("This batch is already signed off.", "status")
    if not (signer_name or "").strip() or not (signer_role or "").strip():
        raise ImportFailure("Give the signer's name and role.", "signer_name")
    report = reconciliation(batch)
    if not (report["balanced"] and report["controls_match"]) or report["pending"]:
        raise ImportFailure(
            "The reconciliation does not balance, so it cannot be signed.", "status"
        )
    snapshot = {k: v for k, v in report.items() if k != "held_rows"}
    with transaction.atomic():
        s = ReconciliationSignoff.objects.create(
            batch=batch,
            signer_name=signer_name.strip(),
            signer_role=signer_role.strip(),
            signed_on=signed_on,
            note=note.strip(),
            snapshot=snapshot,
            recorded_by=actor,
        )
        audit.record(
            actor=actor,
            action="import.signed_off",
            object_type="import_batch",
            object_id=batch.pk,
            after={"signer": s.signer_name, "role": s.signer_role, "signed_on": str(signed_on)},
        )
    return s


def reconciliation_csv(batch) -> str:
    """The same report as a CSV for the file's owner. Counts and reasons only."""
    r = reconciliation(batch)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["section", "item", "source", "pi360", "detail"])
    w.writerow(["summary", "source rows", r["source_rows"], r["accounted_for"], "balanced"
                if r["balanced"] else "NOT BALANCED"])  # fmt: skip
    for k in ("created", "updated", "skipped", "held", "pending", "rolled_back", "quarantined"):
        w.writerow(["bucket", k, "", r[k], ""])
    for c in r["controls"]:
        w.writerow(["cohort", _safe(c["cohort"]), c["source"], c["pi360"],
                    "ok" if c["matches"] else "MISMATCH"])  # fmt: skip
    for h in r["held_rows"]:
        w.writerow(["held", h["row"], "", "", _safe("; ".join(h["reasons"]))])
    return out.getvalue()


def contract(template) -> dict:
    """What a file must look like for this mapping: columns, required fields, and the rules the
    load applies. Published so the source owner can fix files before sending them (T-042)."""
    mapped = set(template.columns.values())
    return {
        "template": str(template),
        "source": template.source,
        "version": template.version,
        "target": template.target,
        "columns": [
            {"source_column": h, "field": f, "required": _fields(template.target).get(f, False)}
            for h, f in template.columns.items()
        ],
        "required_fields_not_mapped": [
            f for f, req in _fields(template.target).items() if req and f not in mapped
        ],
        "rules": placement_rows.IMPORT_RULES
        if template.target == "placements"
        else participants.IMPORT_RULES,
    }


# --- placement review (T-087 stage D2) -------------------------------------------------------


def _need_placements(batch):
    if batch.template.target != "placements":
        raise ImportFailure("This review applies to placement imports only.")
    if batch.status != ImportBatch.VALIDATED:
        raise ImportFailure("Review is possible before the batch is approved.", "status")


def placement_review(batch) -> dict:
    """What a steward must settle before loading a placement batch: the organisation spellings
    grouped into suggested employers (D-064) and the status values with no meaning yet (D-061)."""
    _need_placements(batch)
    rows = batch.rows.exclude(outcome=ImportRow.SKIP).values_list("clean", flat=True)
    orgs = [c.get("organisation", "") for c in rows]
    statuses = [c.get("placement_status", "") for c in batch.rows.values_list("clean", flat=True)]
    return {
        "clusters": employers.build_clusters(
            [o for o in orgs if o and employers.resolve_name(o) is None]
        ),
        "unmapped_statuses": placements.unmapped_values(statuses),
        "held": batch.rows.filter(outcome=ImportRow.HELD).count(),
    }


def decide_employer_group(*, actor, batch, key, spellings, action, employer_id=None) -> dict:
    """A steward's decision on one name group; it is tied to the batch so a rollback reverses it."""
    _need_placements(batch)
    try:
        employers.decide_cluster(
            actor=actor, key=key, spellings=spellings, action=action,
            employer_id=employer_id, source=str(batch.pk),
        )  # fmt: skip
    except ValueError as exc:
        raise ImportFailure(str(exc), "action") from exc
    return placement_review(batch)


def map_placement_status(
    *, actor, batch, source_value, status, pathway="", is_placement=True
) -> dict:
    _need_placements(batch)
    try:
        placements.map_status(
            actor=actor, source_value=source_value, status=status,
            pathway=pathway, is_placement=is_placement,
        )  # fmt: skip
    except ValueError as exc:
        raise ImportFailure(str(exc), "status") from exc
    return placement_review(batch)


@transaction.atomic
def recheck(*, actor, batch) -> ImportBatch:
    """Re-run the checks on held rows after the steward mapped a status or loaded people, so
    rows can move from held to ready without uploading the file again."""
    _need_placements(batch)
    moved = 0
    for row in batch.rows.filter(outcome=ImportRow.HELD):
        checked = placement_rows.check_row(row.clean)
        row.errors, row.warnings, row.clean = checked.errors, checked.warnings, checked.clean
        if not checked.errors:
            row.outcome = ImportRow.SKIP if checked.clean.get("_skip") else ImportRow.CREATE
            moved += 1
        row.save(update_fields=["errors", "warnings", "clean", "outcome"])
    batch.counts = {
        **batch.counts,
        **{k: batch.rows.filter(outcome=k).count() for k in ("create", "update", "held", "skip")},
    }
    batch.save(update_fields=["counts"])
    audit.record(
        actor=actor, action="import.rechecked", object_type="import_batch",
        object_id=batch.pk, after={"released": moved},
    )  # fmt: skip
    return batch
