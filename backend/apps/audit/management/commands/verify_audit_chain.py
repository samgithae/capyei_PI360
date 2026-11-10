from django.core.management.base import BaseCommand, CommandError

from apps.audit import services


class Command(BaseCommand):
    help = "Recompute the audit hash chain and report the first broken event (SEC-09)."

    def handle(self, *args, **options):
        result = services.verify_chain()
        if not result.ok:
            raise CommandError(
                f"Audit chain broken at event {result.first_bad_id}: {result.problem} "
                f"({result.checked} events verified before it)."
            )
        self.stdout.write(f"Audit chain intact: {result.checked} events verified.")
