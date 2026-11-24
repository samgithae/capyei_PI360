"""Enrollment.programme becomes Enrollment.project (D-070, PI360-NEW-069). Rows unchanged."""

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("configuration", "0011_rename_programme_to_project"),
        ("participants", "0011_participant_consent"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="participantenrollment", name="uniq_enrollment_no_per_programme"
        ),
        migrations.RenameField(
            model_name="participantenrollment", old_name="programme", new_name="project"
        ),
        migrations.AlterField(  # points the state at the renamed model; no database change
            model_name="participantenrollment",
            name="project",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="configuration.project",
            ),
        ),
        migrations.AddConstraint(
            model_name="participantenrollment",
            constraint=models.UniqueConstraint(
                fields=["project", "source_enrollment_no"],
                condition=~Q(source_enrollment_no=""),
                name="uniq_enrollment_no_per_project",
            ),
        ),
    ]
