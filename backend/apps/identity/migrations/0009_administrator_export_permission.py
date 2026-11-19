from django.db import migrations


def add(apps, schema_editor):
    """The shipped Administrator role gains de-identified exports (T-071), so it holds every
    permission the M&E analyst role has. Only the system role is touched; nothing is removed."""
    Role = apps.get_model("identity", "Role")
    for role in Role.objects.filter(name="Administrator", is_system=True):
        role.permissions = list(dict.fromkeys([*role.permissions, "exports.deidentified"]))
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("identity", "0008_administrator_retention_permissions")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
