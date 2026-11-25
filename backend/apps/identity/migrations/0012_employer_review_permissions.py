from django.db import migrations

NOTES = "employers.view_feedback_notes"
REVIEW = "employers.review"


def add(apps, schema_editor):
    """Staff who can edit employers keep reading feedback notes; the Administrator also gets the
    review queue. Existing roles only gain permissions, nothing is removed."""
    Role = apps.get_model("identity", "Role")
    for role in Role.objects.filter(is_system=True):
        gain = []
        if "employers.edit" in role.permissions:
            gain.append(NOTES)
        if role.name == "Administrator":
            gain.append(REVIEW)
        if gain:
            role.permissions = list(dict.fromkeys([*role.permissions, *gain]))
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("identity", "0011_scope_kind_project")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
