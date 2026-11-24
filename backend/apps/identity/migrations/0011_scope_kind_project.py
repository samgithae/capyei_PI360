"""Scope kind "programme" becomes "project" (D-070, PI360-NEW-069).

Officers keep exactly the same scope: only the kind's name changes, the value (the project id)
does not. The count of scope rows is checked to be the same before and after.
"""

from django.db import migrations, models


def _rename(apps, old, new):
    Scope = apps.get_model("identity", "ScopeAssignment")
    before = Scope.objects.count()
    Scope.objects.filter(kind=old).update(kind=new)
    if Scope.objects.count() != before:  # pragma: no cover - a safety net, never expected
        raise RuntimeError("Scope rows changed during the rename.")


def forward(apps, schema_editor):
    _rename(apps, "programme", "project")


def backward(apps, schema_editor):
    _rename(apps, "project", "programme")


class Migration(migrations.Migration):
    dependencies = [("identity", "0010_administrator_dataquality_permission")]

    operations = [
        migrations.AlterField(
            model_name="scopeassignment",
            name="kind",
            field=models.CharField(
                choices=[
                    ("project", "Project"),
                    ("cohort", "Cohort"),
                    ("region", "Region"),
                    ("officer", "Officer"),
                ],
                max_length=12,
            ),
        ),
        migrations.RunPython(forward, backward),
    ]
