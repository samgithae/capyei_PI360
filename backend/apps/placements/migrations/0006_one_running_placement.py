"""D-081 (PI360-NEW-070): at most one running placement (placed, not ended) per enrollment.

Before the constraint is added, the data is checked. If any enrollment already has two running
placements the migration stops and reports only how many enrollments are affected: a person
must end the extra placements first (no youth details are printed or changed here)."""

from django.conf import settings
from django.db import migrations, models
from django.db.models import Count


def check_no_second_running(apps, schema_editor):
    Placement = apps.get_model("placements", "Placement")
    clashes = (
        Placement.objects.filter(status="placed", end_date__isnull=True)
        .values("enrollment")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .count()
    )
    if clashes:
        raise RuntimeError(
            f"{clashes} enrollment(s) have more than one running placement. End the extra "
            "placements in PI360 (Placements, filter Current) before running this migration."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("employers", "0012_employer_feedback"),
        ("imports", "0007_rename_programme_to_project"),
        ("participants", "0012_rename_programme_to_project"),
        ("placements", "0005_default_followup_steps"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(check_no_second_running, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="placement",
            constraint=models.UniqueConstraint(
                condition=models.Q(("end_date__isnull", True), ("status", "placed")),
                fields=("enrollment",),
                name="one_running_placement_per_enrollment",
            ),
        ),
    ]
