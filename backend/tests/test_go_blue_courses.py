"""NEW-074: Go Blue courses 001-007 under one project. Synthetic data only: course labels are
programme reference data, not youth information."""

import pytest
from django.core.management import call_command

from apps.configuration import go_blue
from apps.configuration import services as configuration
from apps.configuration.models import Course, Project


@pytest.mark.django_db
def test_seeds_seven_courses_once():
    first = go_blue.seed()
    assert first["project"] and first["courses"] == [c for c, _ in go_blue.COURSES]
    assert go_blue.seed() == {"project": False, "courses": []}
    assert Course.objects.filter(project__code="goblue").count() == 7


@pytest.mark.django_db
def test_siyb_is_included_and_an_existing_project_is_reused():
    Project.objects.create(code="goblue", name="Goblue")
    go_blue.seed()
    assert Project.objects.filter(code__iexact="goblue").count() == 1
    assert Course.objects.get(code="006").name.endswith("(SIYB)")


@pytest.mark.django_db
def test_the_importer_finds_each_course_from_the_sheet_label():
    go_blue.seed()
    project = Project.objects.get(code="goblue")
    labels = [
        "001-vessel repair",
        "002-Maritime Security",
        "003-Hospitality",
        "004-transport and logistics",
        "005-Agri Business",
        "006-Start and Improve Your Business (SIYB)",
        "007-Hospitality-Housekeeping",
    ]
    found = [configuration._find_course(project, label) for label in labels]
    assert all(found) and [c.code for c in found] == [f"00{i}" for i in range(1, 8)]


@pytest.mark.django_db
def test_command_is_safe_to_repeat(capsys):
    call_command("seed_go_blue_courses")
    call_command("seed_go_blue_courses")
    assert "courses created: none" in capsys.readouterr().out
