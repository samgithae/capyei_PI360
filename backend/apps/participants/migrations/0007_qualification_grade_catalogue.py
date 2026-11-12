"""Qualification grade becomes a choice from the seeded catalogue instead of free text.

Text already entered is kept when it matches a grade of the same level (ignoring case); text that
matches nothing is dropped, since it cannot be compared against a required grade."""

import django.db.models.deletion
from django.db import migrations, models


def to_catalogue(apps, schema_editor):
    qual = apps.get_model("participants", "ParticipantQualification")
    grade = apps.get_model("configuration", "QualificationGrade")
    for q in qual.objects.exclude(grade_text=""):
        hit = grade.objects.filter(level_id=q.level_id, name__iexact=q.grade_text.strip()).first()
        if hit:
            q.grade_id = hit.pk
            q.save(update_fields=["grade"])


class Migration(migrations.Migration):
    dependencies = [
        ("participants", "0006_qualification_grade"),
        ("configuration", "0007_seed_qualification_grades"),
    ]
    operations = [
        migrations.RenameField("participantqualification", "grade", "grade_text"),
        migrations.AddField(
            "participantqualification",
            "grade",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="configuration.qualificationgrade",
            ),
        ),
        migrations.RunPython(to_catalogue, migrations.RunPython.noop),
        migrations.RemoveField("participantqualification", "grade_text"),
    ]
