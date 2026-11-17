"""Working-default follow-up schedule (T-066). CAP-YEI has not yet chosen the intervals (D-012)
or the early window (D-028); these are the proposal and an administrator can change them without a
release. They only seed an empty table, so re-running never overrides a changed schedule."""

from django.db import migrations

DEFAULTS = [
    ("early", "30 days", 30),
    ("early", "90 days", 90),
    ("tracer", "6 months", 183),
    ("tracer", "12 months", 365),
    ("tracer", "24 months", 730),
]


def seed(apps, schema_editor):
    Step = apps.get_model("placements", "FollowUpStep")
    if Step.objects.exists():
        return
    Step.objects.bulk_create(
        [Step(kind=k, label=label, offset_days=days) for k, label, days in DEFAULTS]
    )


class Migration(migrations.Migration):
    dependencies = [("placements", "0004_followups")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
