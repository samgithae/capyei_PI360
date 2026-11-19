from django.db import migrations

KEY = "consent_tracking"
DESCRIPTION = (
    "Record each youth's privacy notice and consent (status, notice version, date), show a No "
    "consent badge in the Youth list and offer the fields in youth exports. Off by default. "
    "Provisional until CAP-YEI's data protection lead decides D-015."
)


def seed(apps, schema_editor):
    """Create the switch switched off so administrators can find and change it."""
    FeatureFlag = apps.get_model("configuration", "FeatureFlag")
    FeatureFlag.objects.get_or_create(key=KEY, defaults={"description": DESCRIPTION, "enabled": False})


class Migration(migrations.Migration):
    dependencies = [("configuration", "0009_employer_portal_flags")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
