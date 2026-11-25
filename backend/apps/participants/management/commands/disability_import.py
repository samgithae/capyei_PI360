from django.core.management.base import BaseCommand, CommandError

from apps.participants import services


class Command(BaseCommand):
    help = (
        "NEW-042. With no options: list imported column names that might hold disability, with "
        "row counts and no values. With --column, --yes and --no: show what copying that column "
        "would change. Add --approve (after the data steward and DPO have agreed) to write it."
    )

    def add_arguments(self, parser):
        parser.add_argument("--column")
        parser.add_argument("--yes", nargs="+", default=[], dest="yes_words")
        parser.add_argument("--no", nargs="+", default=[], dest="no_words")
        parser.add_argument("--approve", action="store_true")

    def handle(self, *args, **o):
        if not o["column"]:
            rows = services.disability_import_report()
            if not rows:
                self.stdout.write("No imported extra columns found.")
            for r in rows:
                tag = "  <- name looks relevant" if r["candidate"] else ""
                self.stdout.write(f"{r['key']}: {r['rows']} rows{tag}")
            return
        try:
            out = services.disability_import_apply(
                actor=None, key=o["column"], yes_words=o["yes_words"],
                no_words=o["no_words"], approved=o["approve"],
            )  # fmt: skip
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        mode = "WRITTEN" if o["approve"] else "DRY RUN (nothing written)"
        self.stdout.write(f"{mode}: {out}")
