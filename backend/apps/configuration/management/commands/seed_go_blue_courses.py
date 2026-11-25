from django.core.management.base import BaseCommand

from apps.configuration import go_blue


class Command(BaseCommand):
    help = (
        "Add the Go Blue project and its courses 001-007 (NEW-074). Anything already there is "
        "left alone, so it is safe to run again."
    )

    def handle(self, *args, **options):
        made = go_blue.seed()
        self.stdout.write(
            f"project created: {made['project']}; courses created: "
            f"{', '.join(made['courses']) or 'none'}"
        )
