"""Synthetic development data for trying the UI by hand. Never real data (SEC-14).

Run (development only):
  export DJANGO_DEBUG=1 DATABASE_URL=sqlite:////tmp/pi360-dev.sqlite3
  uv run python manage.py migrate
  uv run python manage.py shell < scripts/seed_dev.py

Creates a Data steward login (no MFA needed): dev.steward / dev-steward-password-1
For referrals: dev.officer / dev-officer-password (Placement officer with three youth assigned);
dev.viewer is the Manager over that officer's caseload.
Youth portal: catherine.macharia@example.org / dev-youth-password-1 (needs a youth named
"Catherine Njeri Macharia" in the dev database; skipped if there is none).
Employer portal for "Synthetic Traders Ltd": dev.boss@synthetic-traders.example
(Company admin) / dev-employer-password-1, and dev.viewer@synthetic-traders.example
(Employer viewer) / dev-employer-password-1. Staff approve opportunities by default.
"""

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.configuration.models import (
    Cohort,
    CohortCourse,
    County,
    Course,
    Project,
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
    prog, _ = Project.objects.get_or_create(code=f"P{n}", defaults={"name": f"Project {n}"})
    course, _ = Course.objects.get_or_create(
        project=prog, code=f"C{n}", defaults={"name": f"Course {n}"}
    )
    cohort, _ = Cohort.objects.get_or_create(
        project=prog,
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
            project=prog,
            institution=inst,
            source_enrollment_no=f"E{n}{i}",
        )
        ParticipantContact.objects.create(
            participant=p, kind="phone", value=f"07000000{n}{i}", is_primary=True
        )

# A deliberate duplicate pair (same person registered in both projects) for T-041 testing.
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
        project=cc.cohort.project,
        institution=inst,
        source_enrollment_no=f"ED{n}",
    )
    ParticipantContact.objects.create(
        participant=p,
        kind="phone",
        value="0711 222 333" if n == "1" else "+254711222333",
        is_primary=True,
    )
# NEW-077: a second duplicate pair where both records have a running placement at the same
# employer from the same date, so merging it waits under "Waiting on conflicts". Synthetic.
from datetime import date as _date  # noqa: E402

from apps.placements import services as _placements  # noqa: E402

for n, cohort in (("3", "K1"), ("4", "K2")):
    if ParticipantEnrollment.objects.filter(source_enrollment_no=f"ED{n}").exists():
        continue
    cc = CohortCourse.objects.get(cohort__code=cohort)
    p = Participant.objects.create(full_name_source="Brian Otieno", gender="male", age_at_source=27)
    e = ParticipantEnrollment.objects.create(
        participant=p,
        cohort_course=cc,
        project=cc.cohort.project,
        institution=inst,
        source_enrollment_no=f"ED{n}",
    )
    ParticipantContact.objects.create(
        participant=p, kind="phone", value="0722 333 444", is_primary=True
    )
    _placements.record_manual(
        actor=None,
        enrollment_id=e.pk,
        pathway="wage",
        start_date=_date(2026, 3, 2),
        employer_name_source="Synthetic Bakery",
        designation="Baker assistant",
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
# A youth portal login for one named dev youth, so the youth view can be tried by hand.
from apps.portal import services as portal  # noqa: E402

_youth = Participant.objects.filter(full_name_source="Catherine Njeri Macharia").first()
if _youth is not None and portal.invite_status(_youth)["state"] == "none":
    _email = "catherine.macharia@example.org"
    if not ParticipantContact.objects.filter(participant=_youth, value=_email).exists():
        ParticipantContact.objects.create(participant=_youth, kind="email", value=_email)
    _admin = User.objects.get(username="dev.admin")
    portal.send_invite(actor=_admin, participant=_youth, email=_email)
    _invite = _youth.youth_account.invites.latest("created_at")
    _token = "dev-seed-token-" + str(_youth.pk)
    import hashlib  # noqa: E402

    _invite.token_hash = hashlib.sha256(_token.encode()).hexdigest()
    _invite.save(update_fields=["token_hash"])
    portal.activate(token=_token, password="dev-youth-password-1")  # noqa: S106
# Employer portal logins for the synthetic company, so both views can be tried by hand.
import hashlib  # noqa: E402

from apps.employer_portal import services as portal_employer  # noqa: E402
from apps.employer_portal.models import EmployerInvite  # noqa: E402
from apps.identity.models import Role  # noqa: E402

for _mail, _name, _role, _owner in (
    ("dev.boss@synthetic-traders.example", "Wanjiru Boss", "Company admin", True),
    ("dev.viewer@synthetic-traders.example", "Kamau Viewer", "Employer viewer", False),
):
    if User.objects.filter(email=_mail).exists():
        continue
    portal_employer.invite(
        actor=User.objects.get(username="dev.admin"),
        employer_id=employer.pk,
        email=_mail,
        full_name=_name,
        role_id=Role.objects.get(name=_role).pk,
        first=_owner,
    )
    _row = EmployerInvite.objects.filter(email=_mail).latest("created_at")
    _token = f"dev-employer-token-{_mail}"  # one per account: the hash is unique
    _row.token_hash = hashlib.sha256(_token.encode()).hexdigest()
    _row.save(update_fields=["token_hash"])
    portal_employer.activate(token=_token, password="dev-employer-password-1")  # noqa: S106
# Demo salary bands, for trying the salary form only. CAP-YEI has not given the real ranges, so
# these are invented, are never seeded by a migration, and are named DEMO so nobody mistakes them.
from decimal import Decimal  # noqa: E402

from apps.configuration.models import SalaryBand, norm  # noqa: E402

for _code, _name, _lo, _hi in (
    ("DEMO-1", "DEMO: under 15,000", None, "14999.99"),
    ("DEMO-2", "DEMO: 15,000 to 29,999", "15000", "29999.99"),
    ("DEMO-3", "DEMO: 30,000 and above", "30000", None),
):
    SalaryBand.objects.get_or_create(
        code=_code,
        defaults={
            "name": _name,
            "name_normalised": norm(_name),
            "min_amount": Decimal(_lo) if _lo else None,
            "max_amount": Decimal(_hi) if _hi else None,
        },
    )
# Draft rule versions for the product owner to review (T-048). Safe to run again.
from apps.intelligence import initial_rules  # noqa: E402

initial_rules.load()
print("seeded")
