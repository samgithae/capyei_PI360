from django.db import migrations

IMPORT = ["imports.run", "imports.commit"]


def add(apps, schema_editor):
    """Placement officers may upload, validate and approve imports (the shipped role gains the
    two permissions). Only the unchanged system role is touched, and nothing is removed."""
    Role = apps.get_model("identity", "Role")
    for role in Role.objects.filter(name="Placement officer", is_system=True):
        role.permissions = list(dict.fromkeys([*role.permissions, *IMPORT]))
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("identity", "0006_employer_invite_permission")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
