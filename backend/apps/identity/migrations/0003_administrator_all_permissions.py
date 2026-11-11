from django.db import migrations

from apps.identity.defaults import ADMIN_ALSO, STAFF_VIEW


def widen_administrator(apps, schema_editor):
    """Give the shipped Administrator role the steward and officer permissions (added, never
    removed, so anything an administrator customised stays)."""
    Role = apps.get_model("identity", "Role")
    role = Role.objects.filter(name="Administrator", is_system=True).first()
    if role:
        role.permissions = list(dict.fromkeys([*role.permissions, *STAFF_VIEW, *ADMIN_ALSO]))
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("identity", "0002_roles_scopes_grants")]
    operations = [migrations.RunPython(widen_administrator, migrations.RunPython.noop)]
