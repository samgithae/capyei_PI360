from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.intelligence import services


class Command(BaseCommand):
    help = (
        "Open a review for each active employer whose recent ratings are low (run nightly; "
        "safe to repeat). Does nothing while the setting employer.review_alerts is 0."
    )

    def handle(self, *args, **options):
        r = services.check_employer_reviews(timezone.localdate())
        if not r["enabled"]:
            self.stdout.write("employer review alerts are off; nothing checked")
            return
        self.stdout.write(f"checked {r['checked']} employers, opened {r['opened']} reviews")
