from django.core.management.base import BaseCommand

from apps.intelligence import initial_rules


class Command(BaseCommand):
    help = (
        "Create the draft rule versions for product owner review (T-048). Rule sets that "
        "already exist are left alone, so it is safe to run again."
    )

    def handle(self, *args, **options):
        created = initial_rules.load()
        self.stdout.write(f"created {len(created)} rule sets: {', '.join(created) or 'none'}")
