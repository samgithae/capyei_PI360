"""Synthetic CAP-YEI demo data for the 23 Nov 2026 meeting changes (PI360-NEW-002). Never real data.

Every name, phone and e-mail here is made up and obviously so: names start with "Synthetic",
phones are 07000001NN, e-mails end in @synthetic.example. Nothing is copied from any CAP-YEI file.

Run (development only; DEBUG must be on):
  cd pi360/backend
  export DJANGO_DEBUG=1 DATABASE_URL="$(sh ../scripts/dev-db.sh url)"
  uv run python manage.py migrate
  uv run python manage.py shell < scripts/seed_capyei_demo.py

Safe to run again: it only adds what is missing.

What it creates (all codes start with SYN-):
- Two projects (stored as Project, D-070): SYN-A "Synthetic Project Alpha", SYN-B "...Beta".
- One training centre and one cohort per project. Both projects have a course with the same code
  and name (SYN-HOSP), which shows today's course-per-project duplication (D-071).
- 6 youth per project, plus one youth enrolled in BOTH projects (the Project Officer edge case,
  D-085).
- Two placement officers, each scoped to one project. They have no usable password: the scope is
  for tests and for an Administrator to inspect under Users. Sign in with your own account.
- Two employers with open opportunities; youth ratings of employer one, two of them low (for
  the future alert rules, D-078).
- A placement chain for the shared youth: a wage job that ended, then a new one with another
  employer (follow-ups, D-080/D-081). One youth is self-employed.
- Self-reported (unverified) skills for every Alpha youth, ready for bulk verification (D-072).
"""

from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

SHARED_ENROLMENT_NOS = ("SYN-A-99", "SYN-B-99")
PER_PROJECT = 6


def _user(username, role_name, scopes):
    from apps.identity import services
    from apps.identity.models import Role

    User = get_user_model()
    user = User.objects.filter(username=username).first()
    if user is None:
        user = User.objects.create_user(username, f"{username}@synthetic.example")
        user.set_unusable_password()
        user.save(update_fields=["password"])
        services.assign_role(actor=None, user=user, role=Role.objects.get(name=role_name))
    if scopes is not None:
        services.set_scopes(actor=None, user=user, scopes=scopes)
    return user


def _youth(code, label, gender, cc, institution):
    """One synthetic youth enrolled in one cohort-course. Returns the enrollment."""
    from apps.participants.models import Participant, ParticipantContact, ParticipantEnrollment

    found = ParticipantEnrollment.objects.filter(source_enrollment_no=code).first()
    if found:
        return found
    p = Participant.objects.create(full_name_source=f"Synthetic Youth {label}", gender=gender)
    ParticipantContact.objects.create(
        participant=p, kind="phone", value=f"07000001{label[-2:]}", is_primary=True
    )
    ParticipantContact.objects.create(
        participant=p, kind="email", value=f"youth.{label.lower()}@synthetic.example"
    )
    return _enrol(p, code, cc, institution)


def _enrol(participant, code, cc, institution):
    from apps.participants.models import ParticipantEnrollment

    return ParticipantEnrollment.objects.create(
        participant=participant,
        cohort_course=cc,
        project=cc.cohort.project,
        institution=institution,
        source_enrollment_no=code,
    )


@transaction.atomic
def seed():
    if not settings.DEBUG:
        raise RuntimeError("Refusing to seed outside development (DEBUG is off).")

    from apps.configuration.models import (
        Cohort,
        CohortCourse,
        County,
        Course,
        Project,
        Sector,
        Skill,
        TrainingInstitution,
    )
    from apps.employers import services as employers
    from apps.employers.models import Employer, EmployerFeedback, Opportunity
    from apps.identity import services as identity
    from apps.participants.models import ParticipantEnrollment, ParticipantSkill
    from apps.placements import services as placements
    from apps.placements.models import Placement

    identity.ensure_default_roles()
    admin = _user("demo.capyei.admin", "Administrator", None)
    today = date.today()

    sector, _ = Sector.objects.get_or_create(
        code="SYN-HOSP", defaults={"name": "Synthetic Hospitality"}
    )
    inst, _ = TrainingInstitution.objects.get_or_create(
        code="SYN-I1",
        defaults={"name": "Synthetic Training Centre One", "county": County.objects.get(code="01")},
    )

    # Two projects, one cohort each, and the same course defined twice (D-071 today).
    ccs = {}
    for letter, word in (("A", "Alpha"), ("B", "Beta")):
        prog, _ = Project.objects.get_or_create(
            code=f"SYN-{letter}", defaults={"name": f"Synthetic Project {word}"}
        )
        course, _ = Course.objects.get_or_create(
            project=prog,
            code="SYN-HOSP",
            defaults={"name": "Synthetic Hospitality", "default_sector": sector},
        )
        cohort, _ = Cohort.objects.get_or_create(
            project=prog,
            institution=inst,
            code=f"SYN-K{letter}",
            defaults={"name": f"Synthetic Cohort {word} 2026", "intake_year": 2026, "batch_no": 1},
        )
        ccs[letter], _ = CohortCourse.objects.get_or_create(cohort=cohort, course=course)

    # Youth: six per project, alternating gender.
    enrolments = {"A": [], "B": []}
    for letter, offset in (("A", 0), ("B", 20)):
        for i in range(1, PER_PROJECT + 1):
            label = f"{letter}{offset + i:02d}"
            gender = "female" if i % 2 else "male"
            enrolments[letter].append(
                _youth(f"SYN-{letter}-{i:02d}", label, gender, ccs[letter], inst)
            )

    # One youth in both projects (D-085): the same person, two enrollments.
    shared = ParticipantEnrollment.objects.filter(
        source_enrollment_no=SHARED_ENROLMENT_NOS[0]
    ).first()
    if shared is None:
        shared = _youth(SHARED_ENROLMENT_NOS[0], "S99", "female", ccs["A"], inst)
    if not ParticipantEnrollment.objects.filter(
        source_enrollment_no=SHARED_ENROLMENT_NOS[1]
    ).exists():
        _enrol(shared.participant, SHARED_ENROLMENT_NOS[1], ccs["B"], inst)

    # Officers scoped to one project each. The scope value is the project id.
    for letter in ("A", "B"):
        prog = Project.objects.get(code=f"SYN-{letter}")
        _user(
            f"demo.officer.{letter.lower()}",
            "Placement officer",
            [("project", str(prog.pk))],
        )

    # Employers and open opportunities.
    emp1, _ = Employer.objects.get_or_create(name="Synthetic Employer One Ltd")
    emp2, _ = Employer.objects.get_or_create(name="Synthetic Employer Two Ltd")
    for emp, titles in ((emp1, ("Synthetic Room Attendant",)), (emp2, ("Synthetic Waiter",))):
        for title in titles:
            Opportunity.objects.get_or_create(
                employer=emp,
                title=title,
                defaults={"status": Opportunity.OPEN, "closing_date": today + timedelta(days=60)},
            )

    # Placement chain for the shared youth: job 1 ended, job 2 running.
    if not Placement.objects.filter(enrollment=shared).exists():
        first = placements.record_manual(
            actor=admin,
            enrollment_id=shared.pk,
            pathway=Placement.WAGE,
            employer_id=emp1.pk,
            designation="Synthetic Room Attendant",
            start_date=today - timedelta(days=200),
        )
        placements.end_episode(
            actor=admin,
            placement_id=first.pk,
            end_date=today - timedelta(days=60),
            exit_reason="Synthetic reason: moved to another employer",
        )
        placements.record_manual(
            actor=admin,
            enrollment_id=shared.pk,
            pathway=Placement.WAGE,
            employer_id=emp2.pk,
            designation="Synthetic Waiter",
            start_date=today - timedelta(days=45),
        )
    # One self-employed youth in Beta.
    self_emp = enrolments["B"][0]
    if not Placement.objects.filter(enrollment=self_emp).exists():
        placements.record_manual(
            actor=admin,
            enrollment_id=self_emp.pk,
            pathway=Placement.SELF,
            start_date=today - timedelta(days=100),
        )

    # Youth ratings of employer one (two low ones, for the alert rules once set).
    if not EmployerFeedback.objects.filter(employer=emp1).exists():
        for days, rating in ((50, 4), (40, 2), (30, 2), (20, 5), (10, 3)):
            employers.add_feedback(
                actor=admin,
                employer=emp1,
                data={
                    "party": EmployerFeedback.YOUTH,
                    "source": EmployerFeedback.CALL,
                    "rating": rating,
                    "note": "Synthetic feedback note",
                    "given_on": today - timedelta(days=days),
                },
            )

    # Self-reported, unverified skills for every Alpha youth (bulk verification, D-072).
    skills = []
    for code, name in (
        ("SYN-COMM", "Synthetic Communication"),
        ("SYN-HKEEP", "Synthetic Housekeeping"),
    ):
        skill, _ = Skill.objects.get_or_create(code=code, defaults={"name": name})
        skills.append(skill)
    for enr in enrolments["A"]:
        for skill in skills:
            ParticipantSkill.objects.get_or_create(
                participant=enr.participant,
                skill=skill,
                defaults={"source": ParticipantSkill.YOUTH},
            )
    return {
        "projects": 2,
        "youth": 2 * PER_PROJECT + 1,
        "shared_participant": str(shared.participant_id),
    }


if __name__ != "seed_capyei_demo":  # run when piped into `manage.py shell`, not when imported
    print("seeded", seed())
