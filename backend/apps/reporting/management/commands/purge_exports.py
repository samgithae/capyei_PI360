from django.core.management.base import BaseCommand

from apps.reporting import exports


class Command(BaseCommand):
    help = "Delete the files of exports past their expiry. The log of who exported what is kept."

    def handle(self, *args, **options):
        n = exports.purge_expired()
        self.stdout.write(f"Deleted {n} expired export file(s).")
