from django.db import migrations

INVITE = "employers.invite_user"


def add(apps, schema_editor):
    """Staff who maintain employers may invite an employer's portal users. Existing roles only
    gain a permission, nothing is removed. The employer portal roles are created by the usual
    start-up seeding."""
    Role = apps.get_model("identity", "Role")
    for role in Role.objects.filter(name__in=["Administrator", "Data steward"], is_system=True):
        role.permissions = list(dict.fromkeys([*role.permissions, INVITE]))
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("identity", "0005_invite_and_youth_role")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
