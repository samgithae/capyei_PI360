"""Bulk-load reference records from a CSV or Excel file (programmes, cohorts, courses,
cohort courses, training institutions, sectors).

Add-only and safe to run twice: a row whose record already exists is skipped, never changed.
A dry run does everything except keep the result, so the user sees exactly what would happen.
Rows that fail are reported with their row number; the valid rows still load."""

import csv
import io
import re
import zipfile
from datetime import date

from django.db import transaction
from openpyxl import load_workbook

from .models import (
    Cohort,
    CohortCourse,
    County,
    Course,
    Programme,
    Sector,
    TrainingInstitution,
    norm,
)
from .services import ConfigError, create_reference

MAX_ROWS = 5_000
MAX_BYTES = 5 * 1024 * 1024
ERROR_CAP = 200

# kind -> list of (field, required, accepted header spellings). Parents are named by code or name.
COLUMNS = {
    "sectors": [("code", True, ()), ("name", True, ())],
    "institutions": [
        ("code", True, ()),
        ("name", True, ()),
        ("kind", False, ("type",)),
        ("county", True, ("county code", "county name")),
    ],
    "programmes": [
        ("code", True, ()),
        ("name", True, ()),
        ("funder", False, ()),
        ("start", False, ("start date",)),
        ("end", False, ("end date",)),
        ("status", False, ()),
    ],
    "courses": [
        ("code", True, ()),
        ("name", True, ()),
        ("programme", True, ("programme code",)),
        ("level", False, ()),
        ("default_sector", False, ("sector", "sector code")),
    ],
    "cohorts": [
        ("code", True, ()),
        ("name", True, ()),
        ("programme", True, ("programme code",)),
        ("institution", True, ("institution code", "training institution", "centre")),
        ("intake_year", True, ("intake year", "year")),
        ("batch_no", True, ("batch", "batch no", "batch number")),
        ("phase", False, ()),
        ("year_of_study", False, ("year of study",)),
        ("start", False, ("start date",)),
        ("end", False, ("end date",)),
        ("status", False, ()),
    ],
    "cohort-courses": [
        ("programme", False, ("programme code",)),
        ("cohort", True, ("cohort code",)),
        ("course", True, ("course code",)),
        ("capacity", False, ()),
    ],
}
INTS = {"intake_year", "batch_no", "phase", "year_of_study", "capacity"}
DATES = {"start", "end"}
EXAMPLE = {
    "sectors": ["SEC01", "Hospitality"],
    "institutions": ["I01", "Example VTC", "vtc", "Nairobi"],
    "programmes": [
        "P01",
        "Example Programme",
        "Example funder",
        "2025-01-01",
        "2027-12-31",
        "active",
    ],
    "courses": ["C01", "Food and Beverage", "P01", "Certificate", "SEC01"],
    "cohorts": [
        "P01-I01-25B1",
        "2025 batch 1",
        "P01",
        "I01",
        "2025",
        "1",
        "1",
        "1",
        "2025-01-15",
        "",
        "active",
    ],
    "cohort-courses": ["P01", "P01-I01-25B1", "C01", "30"],
}


class FileError(Exception):
    pass


def importable(key: str) -> bool:
    return key in COLUMNS


def template_csv(key: str) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([f for f, _, _ in COLUMNS[key]])
    w.writerow(EXAMPLE[key])
    return out.getvalue()


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, date):  # Excel date cells
        return v.date().isoformat() if hasattr(v, "date") else v.isoformat()
    return str(v).strip()


def read_table(name: str, data: bytes) -> list[list[str]]:
    if len(data) > MAX_BYTES:
        raise FileError("The file is larger than 5 MB.")
    lower = name.lower()
    if lower.endswith(".csv"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise FileError("The CSV is not UTF-8 text.") from exc
        table = [[_cell(c) for c in r] for r in csv.reader(io.StringIO(text))]
    elif lower.endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            table = [[_cell(c) for c in r] for r in wb.worksheets[0].iter_rows(values_only=True)]
        except (zipfile.BadZipFile, KeyError, ValueError, IndexError) as exc:
            raise FileError("The Excel file could not be read.") from exc
    else:
        raise FileError("Only .csv and .xlsx files can be imported.")
    # keep original row numbers (1 = header) so error messages match the spreadsheet
    numbered = [(i + 1, r) for i, r in enumerate(table) if any(c for c in r)]
    if len(numbered) < 2:
        raise FileError("The file needs a header row and at least one data row.")
    if len(numbered) - 1 > MAX_ROWS:
        raise FileError(f"More than {MAX_ROWS} rows; split the file.")
    return numbered


def _header_map(key, header_row):
    """Column index for each field, matching headers case- and punctuation-insensitively."""
    seen = {norm(h): i for i, h in enumerate(header_row) if h}
    found, missing = {}, []
    for field, required, aliases in COLUMNS[key]:
        for spelling in (field.replace("_", " "), *aliases):
            if norm(spelling) in seen:
                found[field] = seen[norm(spelling)]
                break
        else:
            if required:
                missing.append(field.replace("_", " "))
    if missing:
        raise FileError("Missing column(s): " + ", ".join(missing) + ".")
    return found


def _int(field, raw):
    try:
        return int(float(raw))
    except ValueError:
        raise ConfigError(field, f"{field.replace('_', ' ')} must be a whole number.") from None


def _date(field, raw):
    raw = raw[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", raw) else raw
    for pattern in (r"^(\d{4})-(\d{2})-(\d{2})$", r"^(\d{1,2})/(\d{1,2})/(\d{4})$"):
        m = re.match(pattern, raw)
        if m:
            a, b, c = (int(x) for x in m.groups())
            try:
                return date(a, b, c) if pattern.startswith(r"^(\d{4})") else date(c, b, a)
            except ValueError:
                break
    raise ConfigError(field, f"{field} must be a date such as 2025-01-31.")


def _find(model, label, value, **scope):
    """A parent by code, else by name. Anything unclear is an error, never a guess."""
    qs = model.objects.filter(**scope)
    hit = list(qs.filter(code__iexact=value)[:2])
    if not hit and hasattr(model, "name_normalised"):
        hit = list(qs.filter(name_normalised=norm(value))[:2])
    if not hit:
        raise ConfigError(label, f"No {label.replace('_', ' ')} matches '{value}'.")
    if len(hit) > 1:
        raise ConfigError(label, f"'{value}' matches more than one {label}; use its code.")
    return hit[0]


def _row_values(key, row):
    data = {}
    for field, required, _ in COLUMNS[key]:
        raw = row.get(field, "")
        if raw == "":
            if required and field != "programme":
                raise ConfigError(field, f"{field.replace('_', ' ')} is required.")
            continue
        data[field] = (
            _int(field, raw) if field in INTS else _date(field, raw) if field in DATES else raw
        )
    if "kind" in data:
        data["kind"] = data["kind"].lower()
    return data


def _load_row(key, actor, row):
    """Returns 'created' or 'skipped'; raises ConfigError for a bad row."""
    d = _row_values(key, row)
    if key == "sectors":
        if Sector.objects.filter(code__iexact=d["code"]).exists():
            return "skipped"
        create_reference(actor=actor, key=key, data=d)
    elif key == "programmes":
        if Programme.objects.filter(code__iexact=d["code"]).exists():
            return "skipped"
        create_reference(actor=actor, key=key, data=d)
    elif key == "institutions":
        if TrainingInstitution.objects.filter(code__iexact=d["code"]).exists():
            return "skipped"
        d["county"] = str(_find(County, "county", d["county"]).pk)
        create_reference(actor=actor, key=key, data=d)
    elif key == "courses":
        prog = _find(Programme, "programme", d["programme"])
        if Course.objects.filter(programme=prog, code__iexact=d["code"]).exists():
            return "skipped"
        d["programme"] = str(prog.pk)
        if "default_sector" in d:
            d["default_sector"] = str(_find(Sector, "sector", d["default_sector"]).pk)
        create_reference(actor=actor, key=key, data=d)
    elif key == "cohorts":
        prog = _find(Programme, "programme", d["programme"])
        if Cohort.objects.filter(programme=prog, code__iexact=d["code"]).exists():
            return "skipped"
        d["programme"] = str(prog.pk)
        d["institution"] = str(_find(TrainingInstitution, "institution", d["institution"]).pk)
        create_reference(actor=actor, key=key, data=d)
    else:  # cohort-courses
        scope = {}
        if "programme" in d:
            scope = {"programme": _find(Programme, "programme", d["programme"])}
        cohort = _find(Cohort, "cohort", d["cohort"], **scope)
        course = _find(Course, "course", d["course"], programme=cohort.programme)
        if CohortCourse.objects.filter(cohort=cohort, course=course).exists():
            return "skipped"
        create_reference(
            actor=actor,
            key=key,
            data={
                "cohort": str(cohort.pk),
                "course": str(course.pk),
                **({"capacity": d["capacity"]} if "capacity" in d else {}),
            },
        )
    return "created"


def run_import(*, actor, key, filename, content, dry_run):
    """Parse and load the file. With ``dry_run`` every change is rolled back at the end."""
    if not importable(key):
        raise FileError("This kind of record cannot be imported.")
    table = read_table(filename, content)
    cols = _header_map(key, table[0][1])
    created = skipped = 0
    errors = []
    with transaction.atomic():
        for number, cells in table[1:]:
            row = {f: (cells[i] if i < len(cells) else "") for f, i in cols.items()}
            try:
                with transaction.atomic():
                    outcome = _load_row(key, actor, row)
            except ConfigError as exc:
                if len(errors) < ERROR_CAP:
                    errors.append({"row": number, "field": exc.field, "message": str(exc)})
                else:
                    errors.append(None)
                continue
            created += outcome == "created"
            skipped += outcome == "skipped"
        if dry_run:
            transaction.set_rollback(True)
    shown = [e for e in errors if e]
    return {
        "dry_run": dry_run,
        "rows": len(table) - 1,
        "created": created,
        "skipped": skipped,
        "failed": len(errors),
        "errors": shown,
    }
