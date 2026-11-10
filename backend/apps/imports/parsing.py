"""Read an uploaded CSV or Excel file into rows of text. Nothing here writes to the database."""

import csv
import io
import zipfile

from openpyxl import load_workbook

MAX_ROWS = 50_000


class FileError(Exception):
    pass


def _cell(v) -> str:
    return "" if v is None else str(v).strip()


def read_rows(name: str, data: bytes) -> tuple[list[str], list[dict]]:
    """Returns (headers, rows) where each row maps header -> text. First sheet only."""
    lower = name.lower()
    if lower.endswith(".csv"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise FileError("The CSV is not UTF-8 text.") from exc
        table = list(csv.reader(io.StringIO(text)))
    elif lower.endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            table = [[_cell(c) for c in r] for r in wb.worksheets[0].iter_rows(values_only=True)]
        except (zipfile.BadZipFile, KeyError, ValueError, IndexError) as exc:
            raise FileError("The Excel file could not be read.") from exc
    else:
        raise FileError("Only .csv and .xlsx files can be imported.")

    table = [r for r in table if any(_cell(c) for c in r)]
    if not table:
        raise FileError("The file has no rows.")
    headers = [_cell(h) for h in table[0]]
    if len(table) - 1 > MAX_ROWS:
        raise FileError(f"More than {MAX_ROWS} rows; split the file.")
    rows = [
        {h: _cell(r[i]) if i < len(r) else "" for i, h in enumerate(headers) if h}
        for r in table[1:]
    ]
    return headers, rows
