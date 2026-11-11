"""Synthetic development data for trying the UI by hand. Never real data (SEC-14).

Run (development only):
  export DJANGO_DEBUG=1 DATABASE_URL=sqlite:////tmp/pi360-dev.sqlite3
  uv run python manage.py migrate
  uv run python manage.py shell < scripts/seed_dev.py

Creates a Data steward login (no MFA needed): dev.steward / dev-steward-password-1
For referrals: dev.officer / dev-officer-password (Placement officer with three youth assigned);
dev.viewer is the Manager over that officer's caseload.
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
# Extra dev-only accounts for checking what other roles can see (Administrator can open Users).
for _name, _role, _pw in (
    ("dev.admin", "Administrator", "dev-admin-password-1"),
    ("dev.viewer", "Manager", "dev-viewer-password-1"),
):
    if not User.objects.filter(username=_name).exists():
        _u = User.objects.create_user(_name, f"{_name}@example.org", _pw)
        services.assign_role(actor=None, user=_u, role=Role.objects.get(name=_role))
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
# Referral workflow (T-046): a placement officer with a caseload, a manager over that caseload,
# and an employer with open opportunities. All synthetic.
from datetime import date, timedelta  # noqa: E402

from apps.employers.models import Employer, Opportunity  # noqa: E402

officer = User.objects.filter(username="dev.officer").first()
if officer is None:
    officer = User.objects.create_user(
        "dev.officer", "dev.officer@example.org", "dev-officer-password"
    )
    services.assign_role(actor=None, user=officer, role=Role.objects.get(name="Placement officer"))
# "self" = the youth assigned to this officer.
services.set_scopes(actor=None, user=officer, scopes=[("officer", "self")])
# The dev manager oversees that officer's caseload (so they can reopen and reassign).
services.set_scopes(
    actor=None,
    user=User.objects.get(username="dev.viewer"),
    scopes=[("officer", str(officer.pk))],
)
Participant.objects.filter(
    enrollments__source_enrollment_no__startswith="E1", assigned_officer__isnull=True
).update(assigned_officer=officer)
employer, _ = Employer.objects.get_or_create(name="Synthetic Traders Ltd")
for title in ("Sales assistant", "Data entry clerk"):
    Opportunity.objects.get_or_create(
        employer=employer,
        title=title,
        defaults={
            "status": Opportunity.OPEN,
            "closing_date": date.today() + timedelta(days=60),
        },
    )
print("seeded")
