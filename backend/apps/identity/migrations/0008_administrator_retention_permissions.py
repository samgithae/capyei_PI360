from django.db import migrations

RETENTION = ["retention.view", "retention.manage"]


def add(apps, schema_editor):
    """The shipped Administrator role gains the data-retention permissions (T-073). Only the
    system role is touched, and nothing is removed."""
    Role = apps.get_model("identity", "Role")
    for role in Role.objects.filter(name="Administrator", is_system=True):
        role.permissions = list(dict.fromkeys([*role.permissions, *RETENTION]))
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("identity", "0007_officer_import_permissions")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
