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
from apps.participants import services as participants

from .models import ImportBatch, ImportRow, MappingTemplate, RecordLineage
from .parsing import FileError, read_rows

CHUNK_SIZE = 500
LOADED = (ImportBatch.COMMITTED, ImportBatch.PARTIAL)


class ImportFailure(Exception):
    def __init__(self, message, field="file"):
        super().__init__(message)
        self.message, self.field = message, field


# --- templates -------------------------------------------------------------


def create_template(*, actor, source, columns, target="participants") -> MappingTemplate:
    if target != "participants":
        raise ImportFailure("Only the participants target exists so far.", "target")
    if not isinstance(columns, dict) or not columns:
        raise ImportFailure("Give a mapping of source column to field.", "columns")
    unknown = sorted(set(columns.values()) - set(participants.FIELDS))
    if unknown:
        raise ImportFailure(f"Unknown target field(s): {', '.join(unknown)}.", "columns")
    missing = [f for f, req in participants.FIELDS.items() if req and f not in columns.values()]
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


# --- upload / dry run ------------------------------------------------------


def _row_hash(raw: dict) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()


def upload(*, actor, template, file_name, data: bytes) -> ImportBatch:
    """Parse and validate. Changes no participant data (the dry run)."""
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
    counts = {"total": len(rows), "create": 0, "update": 0, "held": 0, "skip": 0, "warnings": 0}
    with transaction.atomic():
        batch = ImportBatch.objects.create(
            template=template,
            file_name=file_name[:255],
            file_hash=file_hash,
            uploaded_by=actor,
            duplicate_of=same,
        )
        objs = []
        for n, raw in enumerate(rows, start=1):
            mapped = {template.columns[h]: raw.get(h, "") for h in template.columns}
            checked = participants.check_row(mapped)
            rh = _row_hash(raw)
            outcome = ImportRow.UPDATE if checked.match == "exact" else ImportRow.CREATE
            errors = list(checked.errors)
            if checked.source_key:
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
            elif _already_loaded(template.source, checked.source_key, rh):
                outcome = ImportRow.SKIP
                checked.warnings.append({"field": "", "message": "Already loaded; skipped."})
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
                )
            )
        ImportRow.objects.bulk_create(objs, batch_size=1000)
        batch.counts = counts
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


def approve(*, actor, batch):
    if batch.status != ImportBatch.VALIDATED:
        raise ImportFailure("Only a validated batch can be approved.", "status")
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
                    action, pid, before, after = participants.import_participant(
                        row.clean, batch_ref=str(batch.pk)
                    )
                    RecordLineage.objects.create(
                        row=row,
                        entity="participant",
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
    return batch


# --- rollback --------------------------------------------------------------


def rollback(*, actor, batch, reason):
    """Undo a committed batch while no later batch touched the same records."""
    if batch.status not in LOADED:
        raise ImportFailure("Only a committed batch can be rolled back.", "status")
    if not reason.strip():
        raise ImportFailure("Give a reason.", "reason")
    mine = RecordLineage.objects.filter(row__batch=batch, reverted=False).order_by("-pk")
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
