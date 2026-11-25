"""NEW-006: the course code clash report (006a) and the first, reversible migration step. Course
codes are not yet globally unique: that waits for the data steward to review the report (D-071)."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.configuration import services
from apps.configuration.models import Course, Project

pytestmark = pytest.mark.django_db


@pytest.fixture
def clash(db):
    a = Project.objects.create(code="SYN-A", name="Synthetic A")
    b = Project.objects.create(code="SYN-B", name="Synthetic B")
    Course.objects.create(project=a, code="HOSP", name="Hospitality")
    Course.objects.create(project=b, code="HOSP", name="Hospitality")
    Course.objects.create(project=a, code="ONLY", name="Unique to A")
    return a, b


def test_the_report_lists_a_code_used_in_two_projects_and_nothing_else(clash):
    rows = services.course_code_clashes()
    assert [r["code"] for r in rows] == ["HOSP"]
    assert {u["project"] for u in rows[0]["uses"]} == {"SYN-A", "SYN-B"}
    assert rows[0]["same_name"] is True


def test_a_clash_with_different_names_is_marked(clash):
    a, b = clash
    Course.objects.filter(project=b, code="HOSP").update(
        name="Hotel work", name_normalised="hotel work"
    )
    assert services.course_code_clashes()[0]["same_name"] is False


def test_the_command_reports_without_changing_anything(clash):
    out = StringIO()
    call_command("course_code_report", stdout=out)
    assert "HOSP" in out.getvalue() and "SYN-A" in out.getvalue()
    assert Course.objects.count() == 3


def test_check_fails_while_a_clash_exists_and_passes_when_clear(clash):
    with pytest.raises(CommandError):
        call_command("course_code_report", "--check", stdout=StringIO())
    Course.objects.filter(project__code="SYN-B").delete()
    call_command("course_code_report", "--check", stdout=StringIO())


def test_new_courses_remember_their_project(clash):
    a, _ = clash
    assert Course.objects.get(project=a, code="ONLY").legacy_project_id == a.pk


def _settle():
    """Postgres refuses ALTER TABLE while deferred foreign-key checks are pending in the test's
    transaction, so run them now."""
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_migration_keeps_every_course_and_its_project_and_reverses():
    before = [("configuration", "0013_seed_outcome_lists")]
    after = [("configuration", "0014_course_relax_project")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old = executor.loader.project_state(before).apps
    Project_, Course_ = (
        old.get_model("configuration", "Project"),
        old.get_model("configuration", "Course"),
    )
    a = Project_.objects.create(code="MIG-A", name="A", name_normalised="a")
    b = Project_.objects.create(code="MIG-B", name="B", name_normalised="b")
    Course_.objects.create(project=a, code="X", name="X", name_normalised="x")
    Course_.objects.create(project=b, code="X", name="X", name_normalised="x")
    n = Course_.objects.count()
    _settle()

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    new = executor.loader.project_state(after).apps.get_model("configuration", "Course")
    assert new.objects.count() == n
    assert all(c.legacy_project_id == c.project_id for c in new.objects.all())

    # Simulate a later step that detaches a course, then go back: it gets its project back.
    c = new.objects.first()
    pid = c.project_id
    new.objects.filter(pk=c.pk).update(project=None)
    _settle()
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    back = executor.loader.project_state(before).apps.get_model("configuration", "Course")
    assert back.objects.count() == n and back.objects.get(pk=c.pk).project_id == pid

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
