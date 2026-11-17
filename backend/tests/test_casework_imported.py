"""An imported placement stays as reported; staff may still add its end (T-065)."""

from django.test import Client

from apps.identity import services as identity
from apps.participants.models import Participant
from apps.placements.models import Placement
from tests.test_imports import steward, world  # noqa: F401  (fixtures)
from tests.test_placement_import import load, people, tpl, up  # noqa: F401  (fixtures, helpers)


def test_an_imported_episode_can_be_ended_but_not_edited(tpl, steward, make_user):  # noqa: F811
    load(steward, up(steward, tpl, "P1,E-001,Employment,Acme Traders,,2026-01-05,,"))
    p = Placement.objects.exclude(source_row=None).get()
    officer = make_user("wanjiru", "Placement officer")
    identity.set_scopes(actor=None, user=officer, scopes=[("officer", "self")])
    Participant.objects.update(assigned_officer=officer)
    c = Client()
    c.force_login(officer)
    url = f"/api/v1/placements/{p.pk}"
    assert c.patch(url, {"designation": "x"}, content_type="application/json").status_code == 409
    r = c.post(f"{url}/end", {"end_date": "2026-05-01"}, content_type="application/json")
    assert r.status_code == 200 and r.json()["imported"] and not r.json()["can"]["edit"]
