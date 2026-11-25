"""Working list of rating criteria (NEW-026). D-077 is still open: CAP-YEI has not approved this
list, so administrators can rename, add or switch criteria off."""

from django.db import migrations

WORKING = [
    ("work-quality", "Quality of work"),
    ("punctuality", "Punctuality and attendance"),
    ("teamwork", "Teamwork and attitude"),
    ("supervision", "Supervision and treatment of the young person"),
]


def seed(apps, schema_editor):
    model = apps.get_model("employers", "FeedbackCriterion")
    for i, (code, name) in enumerate(WORKING):
        model.objects.get_or_create(code=code, defaults={"name": name, "position": i})


class Migration(migrations.Migration):
    dependencies = [("employers", "0013_feedback_criteria")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
