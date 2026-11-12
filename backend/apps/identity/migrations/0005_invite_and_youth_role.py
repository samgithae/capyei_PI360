from django.db import migrations

INVITE = "participants.invite"
YOUTH = {
    "name": "Youth",
    "description": "A youth signed in to their own record. Sees and edits only that record.",
    "scope_mode": "assigned",
    "active": True,
    "permissions": ["youth.self_service"],
    "is_system": True,
}


def add(apps, schema_editor):
    """Staff who may create youth may invite them; add the Youth role. Existing roles only gain
    a permission, nothing is removed."""
    Role = apps.get_model("identity", "Role")
    for role in Role.objects.filter(name__in=["Administrator", "Data steward"], is_system=True):
        role.permissions = list(dict.fromkeys([*role.permissions, INVITE]))
        role.save(update_fields=["permissions"])
    Role.objects.get_or_create(name=YOUTH["name"], defaults=YOUTH)


class Migration(migrations.Migration):
    dependencies = [("identity", "0004_administrator_rule_permissions")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
