"""Rename Programme to Project everywhere (D-070, B1; task PI360-NEW-069).

A pure rename: the table, the foreign-key columns and the constraints keep their rows. No drop
and recreate of data. The constraints are removed and re-added only because their names and
field lists mention the old name; the rows they protect are unchanged.

Stored reference kinds ("programmes") on aliases and name history become "projects". The audit
trail is not rewritten: it is hash-chained, and history keeps the name used at the time.
"""

from django.db import migrations, models

KIND_OLD, KIND_NEW = "programmes", "projects"


def kinds_forward(apps, schema_editor):
    for name in ("ReferenceAlias", "ReferenceLabel"):
        apps.get_model("configuration", name).objects.filter(kind=KIND_OLD).update(kind=KIND_NEW)


def kinds_backward(apps, schema_editor):
    for name in ("ReferenceAlias", "ReferenceLabel"):
        apps.get_model("configuration", name).objects.filter(kind=KIND_NEW).update(kind=KIND_OLD)


def permissions_forward(apps, schema_editor):
    """Django's own model permissions (add_programme, ...) follow the model name."""
    Permission = apps.get_model("auth", "Permission")
    for p in Permission.objects.filter(
        content_type__app_label="configuration", codename__endswith="_programme"
    ):
        p.codename = p.codename.replace("_programme", "_project")
        p.name = p.name.replace("programme", "project")
        p.save(update_fields=["codename", "name"])


def permissions_backward(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    for p in Permission.objects.filter(
        content_type__app_label="configuration", codename__endswith="_project"
    ):
        p.codename = p.codename.replace("_project", "_programme")
        p.name = p.name.replace("project", "programme")
        p.save(update_fields=["codename", "name"])


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("configuration", "0010_consent_tracking_flag"),
        # participants 0001 creates the FK to configuration.programme; it must
        # exist before the model is renamed, or a fresh database cannot be built.
        ("participants", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="programme", name="uniq_programme_code"),
        migrations.RemoveConstraint(model_name="course", name="uniq_course_code"),
        migrations.RemoveConstraint(model_name="cohort", name="uniq_cohort_identity"),
        migrations.RemoveConstraint(model_name="cohort", name="uniq_cohort_code"),
        migrations.RenameModel(old_name="Programme", new_name="Project"),
        migrations.RenameField(model_name="course", old_name="programme", new_name="project"),
        migrations.RenameField(model_name="cohort", old_name="programme", new_name="project"),
        migrations.AddConstraint(
            model_name="project",
            constraint=models.UniqueConstraint(fields=["code"], name="uniq_project_code"),
        ),
        migrations.AddConstraint(
            model_name="course",
            constraint=models.UniqueConstraint(fields=["project", "code"], name="uniq_course_code"),
        ),
        migrations.AddConstraint(
            model_name="cohort",
            constraint=models.UniqueConstraint(
                fields=[
                    "project",
                    "institution",
                    "intake_year",
                    "batch_no",
                    "phase",
                    "year_of_study",
                ],
                name="uniq_cohort_identity",
            ),
        ),
        migrations.AddConstraint(
            model_name="cohort",
            constraint=models.UniqueConstraint(fields=["project", "code"], name="uniq_cohort_code"),
        ),
        migrations.RunPython(kinds_forward, kinds_backward),
        migrations.RunPython(permissions_forward, permissions_backward),
    ]
