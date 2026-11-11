from django.db import migrations

RULES = ["intelligence.manage_rules", "intelligence.approve_rules"]


def widen_administrator(apps, schema_editor):
    """Give the shipped Administrator role the rule-version permissions (T-047). Added, never
    removed, so anything an administrator customised stays."""
    Role = apps.get_model("identity", "Role")
    role = Role.objects.filter(name="Administrator", is_system=True).first()
    if role:
        role.permissions = list(dict.fromkeys([*role.permissions, *RULES]))
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("identity", "0003_administrator_all_permissions")]
    operations = [migrations.RunPython(widen_administrator, migrations.RunPython.noop)]
