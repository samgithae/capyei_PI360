"""T-086: Go Blue historical enrollment dry run (counts only; prints no personal values).

Run against a THROWAWAY database, never a shared one (SEC-14, D-035):
  export DJANGO_DEBUG=1 DATABASE_URL=sqlite:////path/to/throwaway.sqlite3
  uv run python manage.py migrate
  GB_CSV="/path/Go Blue ... - Enrollment.csv" GB_OUT=/path/prepared.csv \
    uv run python manage.py shell < scripts/go_blue_dry_run.py

What it does, in order:
 1. Builds reference data from the file's own distinct values (programme GB, courses, institutions,
    cohorts, offerings). The file has no codes, so the codes below are proposals for CAP-YEI.
 2. Writes a prepared copy: cohort and course replaced by codes, county name by county code.
    (Normalisation rules; the source value is kept in the original file.) National ID is left
    out on purpose: it is a restricted field, not an importable source identifier (D-064).
 3. Validates, approves and loads it through apps.imports.services, then reconciles by cohort.
"""

import csv
import os
import re
from collections import Counter

from django.conf import settings

from apps.configuration.models import (
    Cohort,
    CohortCourse,
    County,
    Course,
    Programme,
    TrainingInstitution,
)
from apps.identity import services as identity
from apps.identity.models import Role
from apps.imports import services as imp
from apps.participants.models import ParticipantEnrollment

assert settings.DEBUG, "Refusing to run outside development."
SRC, OUT = os.environ["GB_CSV"], os.environ["GB_OUT"]
rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
COHORT = re.compile(r"^(.+?) VTC - (\d{4}) Batch (\d+)-Phase (\d+)-Year (\d+)$")
print(f"source rows: {len(rows)}")

# 1. reference data -------------------------------------------------------------------------
prog, _ = Programme.objects.get_or_create(code="GB", defaults={"name": "Go Blue"})
county_by_name = {c.name.lower(): c for c in County.objects.all()}
print(f"counties in reference data: {len(county_by_name)}")
inst_county = {}
for r in rows:
    inst_county.setdefault(r["VTC Name"], r["County"])
insts = {}
for i, name in enumerate(sorted(inst_county), start=1):
    county = county_by_name.get(inst_county[name].lower())
    if county is None:
        raise SystemExit(f"County name not in reference data: {inst_county[name]!r}")
    insts[name], _ = TrainingInstitution.objects.get_or_create(
        code=f"I{i:02d}", defaults={"name": name, "county": county}
    )
courses = {}
for label in sorted({r["Course"] for r in rows}):
    code, _, name = label.partition("-")
    courses[label], _ = Course.objects.get_or_create(
        programme=prog, code=code.strip(), defaults={"name": name.strip()}
    )
cohorts, offerings = {}, {}
for label in sorted({r["Cohort/Batch"] for r in rows}):
    inst_name, year, batch, phase, yos = COHORT.match(label).groups()
    code = f"{insts[inst_name + ' VTC'].code}-{year[2:]}B{batch}P{phase}Y{yos}"
    cohorts[label], _ = Cohort.objects.get_or_create(
        programme=prog,
        code=code,
        defaults=dict(
            name=label,
            institution=insts[inst_name + " VTC"],
            intake_year=int(year),
            batch_no=int(batch),
            phase=int(phase),
            year_of_study=int(yos),
        ),
    )
for r in rows:
    key = (r["Cohort/Batch"], r["Course"])
    if key not in offerings:
        offerings[key], _ = CohortCourse.objects.get_or_create(
            cohort=cohorts[key[0]], course=courses[key[1]]
        )
print(
    f"reference: {len(insts)} institutions, {len(courses)} courses, "
    f"{len(cohorts)} cohorts, {len(offerings)} offerings"
)

# 2. prepared copy ---------------------------------------------------------------------------
fields = ["name", "age", "gender", "county_code", "cohort_code", "course_code",
          "enrollment_no", "phone"]  # fmt: skip
with open(OUT, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(fields)
    for r in rows:
        w.writerow([
            r["Trainee Name"], r["Age"], r["Gender"],
            county_by_name[r["County"].lower()].code,
            cohorts[r["Cohort/Batch"]].code, courses[r["Course"]].code,
            r["EnrollmentNo"], r["Phone Number(Main)"],
        ])  # fmt: skip

# 3. import ----------------------------------------------------------------------------------
identity.ensure_default_roles()
from django.contrib.auth import get_user_model  # noqa: E402

User = get_user_model()
steward, _ = User.objects.get_or_create(username="dry.run", defaults={"email": "dry@example.org"})
identity.assign_role(actor=None, user=steward, role=Role.objects.get(name="Data steward"))
columns = {
    "name": "full_name", "age": "age", "gender": "gender", "county_code": "county_code",
    "cohort_code": "cohort_code", "course_code": "course_code", "enrollment_no": "enrollment_no",
    "phone": "phone",
}  # fmt: skip
tpl = imp.create_template(actor=steward, source="go-blue-enrollment", columns=columns)
batch = imp.upload(
    actor=steward,
    template=tpl,
    file_name="go-blue-prepared.csv",
    data=open(OUT, "rb").read(),
    defaults={"programme_code": "GB"},
)
print("validation counts:", batch.counts)
held = Counter()
warned = Counter()
for row in batch.rows.exclude(errors=[]):
    for e in row.errors:
        held[(e["field"], e["message"].split("'")[0][:60])] += 1
for row in batch.rows.exclude(warnings=[]):
    for e in row.warnings:
        warned[(e["field"], e["message"].split("'")[0][:70])] += 1
print("blocking reasons:", dict(held))
print("warning reasons:", dict(warned))
imp.approve(actor=steward, batch=batch)
batch = imp.commit(actor=steward, batch=batch)
print("batch status:", batch.status)
rec = imp.reconciliation(batch)
print("reconciliation balanced:", rec["balanced"], "| controls match:", rec["controls_match"])
print("reconciliation:", {k: v for k, v in rec.items() if k != "held_rows"})

per_file = Counter(r["Cohort/Batch"] for r in rows)
bad = [
    lab for lab, n in per_file.items()
    if ParticipantEnrollment.objects.filter(cohort_course__cohort=cohorts[lab]).count() != n
]  # fmt: skip
print(f"cohorts where loaded count != file count: {len(bad)} of {len(per_file)}")
print("participants loaded:", ParticipantEnrollment.objects.count())
