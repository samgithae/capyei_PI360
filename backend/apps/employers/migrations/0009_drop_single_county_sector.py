"""Schema step: the single columns are dropped once 0008 has copied them into the links."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("employers", "0008_copy_single_to_many")]

    operations = [
        migrations.RemoveField(
            model_name="employer",
            name="county",
        ),
        migrations.RemoveField(
            model_name="employer",
            name="sector",
        ),
        migrations.RemoveField(
            model_name="opportunity",
            name="county",
        ),
        migrations.RemoveField(
            model_name="opportunity",
            name="sector",
        ),
    ]
