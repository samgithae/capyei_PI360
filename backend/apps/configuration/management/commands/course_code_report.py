from django.core.management.base import BaseCommand, CommandError

from apps.configuration import services


class Command(BaseCommand):
    help = (
        "NEW-006a. List course codes used under more than one project, with names only. It "
        "changes nothing. With --check it exits with an error while any clash exists, which is "
        "the condition for making course codes globally unique (D-071)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true")

    def handle(self, *args, **options):
        clashes = services.course_code_clashes()
        if not clashes:
            self.stdout.write("No course code is used under more than one project.")
            return
        for row in clashes:
            kind = "same name" if row["same_name"] else "different names"
            self.stdout.write(f"{row['code']} ({kind})")
            for use in row["uses"]:
                self.stdout.write(f"    {use['project']}: {use['name']}")
        if options["check"]:
            raise CommandError(f"{len(clashes)} course code(s) clash. Resolve them first.")
