"""NEW-074: the Go Blue course list, 001 to 007, as courses under one project.

The codes and labels are the ones in the Go Blue sheet's Course column (counts only were read,
never a youth row). Whether 006 (SIYB, one trainee) is a real course is still a question for
CAP-YEI (B5 in the decision pack), so it is created like the others and can be retired.
Sharing one course across projects waits for NEW-006 / D-071; until then the courses belong to
the single Go Blue project. Safe to run again: anything already there is left alone."""

from django.db import transaction

from apps.audit import services as audit

from .models import Course, Project, ReferenceLabel

PROJECT_CODE, PROJECT_NAME = "goblue", "Go Blue"

COURSES = [
    ("001", "Vessel repair"),
    ("002", "Maritime Security"),
    ("003", "Hospitality"),
    ("004", "Transport and logistics"),
    ("005", "Agri Business"),
    ("006", "Start and Improve Your Business (SIYB)"),
    ("007", "Hospitality-Housekeeping"),
]


@transaction.atomic
def seed(*, actor=None) -> dict:
    """Create the project and any missing courses. Returns what was created."""
    project = Project.objects.filter(code__iexact=PROJECT_CODE).first()
    made = {"project": False, "courses": []}
    if project is None:
        project = Project.objects.create(code=PROJECT_CODE, name=PROJECT_NAME)
        made["project"] = True
    for code, name in COURSES:
        if Course.objects.filter(project=project, code__iexact=code).exists():
            continue
        course = Course.objects.create(project=project, code=code, name=name)
        ReferenceLabel.objects.create(kind="courses", object_id=course.pk, name=name)
        audit.record(
            actor=actor,
            action="reference.created",
            object_type="reference.courses",
            object_id=course.pk,
            after={"code": code, "name": name, "project": project.code},
        )
        made["courses"].append(code)
    return made
