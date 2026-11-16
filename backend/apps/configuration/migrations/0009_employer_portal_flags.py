from django.db import migrations

FLAGS = [
    (
        "employer_mfa_required",
        "Require a second factor (authenticator app) for employer portal users. Set the roles "
        "to limit it, for example to Company admin only. Off by default.",
    ),
    (
        "employer_self_publish",
        "Let employers open their own opportunities without staff approval. Off by default: "
        "staff approve every opportunity an employer submits.",
    ),
]


def seed(apps, schema_editor):
    """Create the switches switched off so administrators can find and change them."""
    FeatureFlag = apps.get_model("configuration", "FeatureFlag")
    for key, description in FLAGS:
        FeatureFlag.objects.get_or_create(
            key=key, defaults={"description": description, "enabled": False}
        )


class Migration(migrations.Migration):
    dependencies = [("configuration", "0008_seed_more_skills")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
