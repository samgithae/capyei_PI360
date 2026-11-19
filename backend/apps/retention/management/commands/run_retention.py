"""The scheduled retention job (T-073). Dry run unless --apply; only classes with an approved
period are touched. Prints counts only."""

from django.core.management.base import BaseCommand

from apps.retention import services


class Command(BaseCommand):
    help = "Report (default) or apply the approved data-retention rules."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Actually clear the values.")

    def handle(self, *args, apply=False, **options):
        run = services.run(actor=None, apply=apply)
        self.stdout.write(f"{'APPLIED' if apply else 'DRY RUN'} {run['at']}")
        for code, r in run["results"].items():
            self.stdout.write(f"  {code}: " + ", ".join(f"{k}={v}" for k, v in r.items()))
