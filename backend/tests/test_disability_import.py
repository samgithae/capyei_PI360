# ruff: noqa: F811
"""Disability from imported sheets (NEW-042, D-082): a names-and-counts report, then an opt-in
mapping that copies nothing without approval. Synthetic data only."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.audit.models import AuditEvent
from apps.configuration.models import FeatureFlag
from apps.participants import services
from apps.participants.models import Participant

from .test_participants import enrol, world  # noqa: F401

pytestmark = pytest.mark.django_db
COL = "Special needs?"


@pytest.fixture
def sheet(world):
    """Four youth: Yes, No, an unclear answer, and one already answered by staff."""
    out = {}
    for name, cell in (("a", "Yes"), ("b", "no"), ("c", "maybe"), ("d", "No")):
        p = Participant.objects.create(full_name_source=f"Synthetic {name}")
        e = enrol(world, p)
        e.extra = {COL: cell, "Hobby": "football"}
        e.save()
        out[name] = p
    Participant.objects.filter(pk=out["d"].pk).update(disability="yes", disability_source="staff")
    return out


def test_the_report_names_columns_and_counts_rows_and_holds_no_values(sheet):
    rows = services.disability_import_report()
    assert rows[0] == {"key": COL, "rows": 4, "candidate": True}
    assert {"key": "Hobby", "rows": 4, "candidate": False} in rows
    assert "Yes" not in str(rows) and "football" not in str(rows)


def test_a_dry_run_changes_nothing(sheet):
    out = services.disability_import_apply(
        actor=None, key=COL, yes_words=["yes"], no_words=["no"], approved=False
    )
    assert out["would_set"] == 2 and out["set"] == 0 and out["unmatched"] == 1
    assert out["already_recorded"] == 1
    assert not Participant.objects.filter(disability_source="import").exists()


def test_approval_is_not_enough_while_the_feature_is_off(sheet):
    with pytest.raises(ValueError):
        services.disability_import_apply(
            actor=None, key=COL, yes_words=["yes"], no_words=["no"], approved=True
        )


def test_an_approved_mapping_writes_import_answers_only_where_nothing_was_recorded(sheet):
    FeatureFlag.objects.create(key="participants.disability", enabled=True)
    out = services.disability_import_apply(
        actor=None, key=COL, yes_words=["Yes"], no_words=["NO"], approved=True
    )
    assert out["set"] == 2
    a, b, c, d = (Participant.objects.get(pk=sheet[k].pk) for k in "abcd")
    assert (a.disability, a.disability_source, a.disability_description) == ("yes", "import", "")
    assert (b.disability, b.disability_source) == ("no", "import")
    assert c.disability == "not_recorded"  # unclear text is never guessed
    assert (d.disability, d.disability_source) == ("yes", "staff")  # staff answer kept
    ev = AuditEvent.objects.get(action="participant.disability_imported")
    assert "Yes" not in str(ev.after) and ev.after["set"] == 2


def test_overlapping_or_empty_word_lists_are_refused(sheet):
    for yes, no in ((["x"], ["x"]), ([], ["no"])):
        with pytest.raises(ValueError):
            services.disability_import_apply(
                actor=None, key=COL, yes_words=yes, no_words=no, approved=False
            )


def test_the_command_lists_then_dry_runs_and_refuses_to_write_when_off(sheet):
    out = StringIO()
    call_command("disability_import", stdout=out)
    assert COL in out.getvalue() and "football" not in out.getvalue()
    out = StringIO()
    call_command("disability_import", "--column", COL, "--yes", "yes", "--no", "no", stdout=out)
    assert "DRY RUN" in out.getvalue()
    with pytest.raises(CommandError):
        call_command(
            "disability_import", "--column", COL, "--yes", "yes", "--no", "no", "--approve",
            stdout=StringIO(),
        )  # fmt: skip
