"""Programme was renamed to Project (D-070, PI360-NEW-069).

Files people already have keep working: every importer still accepts the old "Programme" and
"Programme code" headers. Stored import state is renamed by migration, but only field names:
a file's own headers and a youth's own answers are never changed. All data here is made up.
"""

import importlib

import pytest

from apps.configuration import importer
from apps.imports import placement_rows
from apps.imports import services as imports
from apps.participants import capability_import

rename = importlib.import_module("apps.imports.migrations.0007_rename_programme_to_project")


@pytest.mark.django_db
@pytest.mark.parametrize("header", ["Programme", "Programme Code", "Project", "Project code"])
def test_youth_import_maps_old_and_new_project_headers(header):
    data = f"Full name,{header},Cohort\nTest Person,P01,C01\n".encode()
    shape = imports.inspect(file_name="youth.csv", data=data)
    assert shape["suggested"][header] == "project_code"


@pytest.mark.parametrize("header", ["Programme", "programme code", "PROJECT"])
def test_placement_import_accepts_old_project_header(header):
    assert placement_rows.SYNONYMS[imports._norm(header)] == "project_code"


@pytest.mark.parametrize("key", ["courses", "cohorts", "cohort-courses"])
@pytest.mark.parametrize("header", ["Programme", "Programme code", "Project"])
def test_setup_import_accepts_old_project_header(key, header):
    required = [f for f, req, _ in importer.COLUMNS[key] if req and f != "project"]
    row = [f.replace("_", " ") for f in required] + [header]
    assert importer._header_map(key, row)["project"] == len(row) - 1


@pytest.mark.parametrize("header", ["Programme", "Programme Code", "Project Code"])
def test_capability_import_accepts_old_project_header(header):
    cols = capability_import._columns(["Enrollment No", header, "Type", "Value"])
    assert cols["project"] == 1


def test_migration_renames_field_names_only():
    names = rename.FORWARD
    # A template maps the file's own headers to fields: headers stay, fields are renamed.
    assert rename._rename({"programme": "programme_code"}, names, "values") == {
        "programme": "project_code"
    }
    # Clean rows are keyed by field; a youth's answer that happens to read "programme" stays.
    clean = {"programme_code": "P01", "extra:Notes": "programme", "_proposed": [{"programme": 1}]}
    assert rename._rename(clean, names, "keys") == {
        "project_code": "P01",
        "extra:Notes": "programme",
        "_proposed": [{"project": 1}],
    }
    errors = [{"field": "programme_code", "message": "Unknown programme 'P9'."}]
    assert rename._rename(errors, names, "field") == [
        {"field": "project_code", "message": "Unknown programme 'P9'."}
    ]


def test_migration_round_trips():
    clean = {"programme_code": "P01", "programme_id": 3, "name": "programme"}
    there = rename._rename(clean, rename.FORWARD, "keys")
    assert rename._rename(there, rename.BACKWARD, "keys") == clean
