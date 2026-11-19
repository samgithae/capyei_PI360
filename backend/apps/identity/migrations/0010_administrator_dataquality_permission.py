from django.db import migrations


def add(apps, schema_editor):
    """The shipped Administrator role gains data quality and MIS corrections (T-074), so it holds
    every permission the data steward role has. Only the system role is touched."""
    Role = apps.get_model("identity", "Role")
    for role in Role.objects.filter(name="Administrator", is_system=True):
        role.permissions = list(dict.fromkeys([*role.permissions, "dataquality.review"]))
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("identity", "0009_administrator_export_permission")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
