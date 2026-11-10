"""Synthetic development data for trying the UI by hand. Never real data (SEC-14).

Run (development only):
  export DJANGO_DEBUG=1 DATABASE_URL=sqlite:////tmp/pi360-dev.sqlite3
  uv run python manage.py migrate
  uv run python manage.py shell < scripts/seed_dev.py

Creates a Data steward login (no MFA needed): dev.steward / dev-steward-password-1
"""

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.configuration.models import (
    Cohort,
    CohortCourse,
    County,
    Course,
    Programme,
    Sector,
    TrainingInstitution,
)
from apps.identity import services
from apps.identity.models import Role
from apps.participants.models import Participant, ParticipantContact, ParticipantEnrollment

assert settings.DEBUG, "Refusing to seed outside development."
services.ensure_default_roles()
User = get_user_model()
if not User.objects.filter(username="dev.steward").exists():
    u = User.objects.create_user("dev.steward", "dev@example.org", "dev-steward-password-1")
    services.assign_role(actor=None, user=u, role=Role.objects.get(name="Data steward"))
inst, _ = TrainingInstitution.objects.get_or_create(
    code="I1", defaults={"name": "Synthetic College", "county": County.objects.get(code="01")}
)
Sector.objects.get_or_create(code="ICT", defaults={"name": "ICT"})
for n in ("1", "2"):
    prog, _ = Programme.objects.get_or_create(code=f"P{n}", defaults={"name": f"Programme {n}"})
    course, _ = Course.objects.get_or_create(
        programme=prog, code=f"C{n}", defaults={"name": f"Course {n}"}
    )
    cohort, _ = Cohort.objects.get_or_create(
        programme=prog,
        institution=inst,
        code=f"K{n}",
        defaults=dict(name=f"Cohort {n}", intake_year=2025, batch_no=int(n), phase="1"),
    )
    cc, _ = CohortCourse.objects.get_or_create(cohort=cohort, course=course)
    for i in range(3):
        if ParticipantEnrollment.objects.filter(source_enrollment_no=f"E{n}{i}").exists():
            continue
        p = Participant.objects.create(
            full_name_source=f"Person {n}{i}", gender="female" if i % 2 else "male"
        )
        ParticipantEnrollment.objects.create(
            participant=p,
            cohort_course=cc,
            programme=prog,
            institution=inst,
            source_enrollment_no=f"E{n}{i}",
        )
        ParticipantContact.objects.create(
            participant=p, kind="phone", value=f"07000000{n}{i}", is_primary=True
        )

# A deliberate duplicate pair (same person registered in both programmes) for T-041 testing.
for n, age in (("1", 24), ("2", 25)):
    if ParticipantEnrollment.objects.filter(source_enrollment_no=f"ED{n}").exists():
        continue
    cc = CohortCourse.objects.get(cohort__code=f"K{n}")
    p = Participant.objects.create(
        full_name_source="Grace Akinyi", gender="female", age_at_source=age
    )
    ParticipantEnrollment.objects.create(
        participant=p,
        cohort_course=cc,
        programme=cc.cohort.programme,
        institution=inst,
        source_enrollment_no=f"ED{n}",
    )
    ParticipantContact.objects.create(
        participant=p,
        kind="phone",
        value="0711 222 333" if n == "1" else "+254711222333",
        is_primary=True,
    )
print("seeded")
