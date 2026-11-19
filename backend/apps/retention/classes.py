"""The data classes the retention job knows how to reduce (T-073).

Each class says what it is, what reducing it removes, how to count what is due and how to do it.
Adding a class is adding one entry here, with the owning module supplying the two functions
through its services. Participant anonymisation, the audit log, placements and follow-ups are
left out on purpose until D-015 settles their periods and basis."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from apps.imports import services as imports


@dataclass(frozen=True)
class DataClass:
    code: str
    label: str
    description: str
    removes: str  # what reducing it clears, in plain words
    keeps: str  # what stays, in plain words
    minimum_days: int
    count: Callable[[datetime], dict]
    reduce: Callable[[datetime], dict]


IMPORT_ROWS = DataClass(
    code="import_rows",
    label="Imported source rows",
    description=(
        "The text of each spreadsheet row kept with a loaded import batch, so a batch could "
        "be checked or rolled back. Only batches whose reconciliation has been signed off "
        "are touched."
    ),
    removes=(
        "the row's own values (raw and cleaned), the field-by-field differences, and the "
        "before/after copies of the records it changed"
    ),
    keeps=(
        "row numbers, outcomes, error and warning messages (which never hold values), the "
        "cohort code, hashes used to skip a re-uploaded file, the sign-off and its snapshot"
    ),
    minimum_days=30,
    count=imports.retention_count,
    reduce=imports.retention_reduce,
)

REGISTRY: dict[str, DataClass] = {c.code: c for c in (IMPORT_ROWS,)}
