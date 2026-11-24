from django.apps import AppConfig


class CaseworkConfig(AppConfig):
    name = "apps.casework"
    label = "casework"
    verbose_name = "Case management"

    def ready(self):
        # NEW-077: the merge in participants asks this coordinator for the conflicts it cannot
        # see itself (placements, referrals, portal accounts).
        from apps.participants import services as participants

        from . import merge_checks

        participants.add_check(merge_checks.check)
