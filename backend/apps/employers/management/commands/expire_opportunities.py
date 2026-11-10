from django.core.management.base import BaseCommand

from apps.employers import services


class Command(BaseCommand):
    help = "Mark open opportunities past their closing date as expired (run daily; idempotent)."

    def handle(self, *args, **options):
        self.stdout.write(f"expired {services.expire_due()} opportunities")
