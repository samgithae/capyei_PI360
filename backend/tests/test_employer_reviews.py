"""NEW-028/029: the employer review queue and who may read feedback notes. Synthetic data."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.employers.models import Employer, EmployerFeedback, EmployerReview
from apps.intelligence import services


def api(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def employer(db):
    return Employer.objects.create(name="Acme")


def rate(employer, *ratings, note=""):
    for r in ratings:
        EmployerFeedback.objects.create(
            employer=employer, party="employer", source="call", rating=r, note=note,
            given_on=timezone.localdate() - timedelta(days=1),
        )  # fmt: skip


def turn_on(user):
    services.update_settings(actor=user, values={"employer.review_alerts": 1})


def test_nothing_fires_while_the_setting_is_off(employer):
    rate(employer, 1, 1, 1)
    out = services.check_employer_reviews(timezone.localdate())
    assert out == {"enabled": False, "checked": 0, "opened": 0}
    assert not EmployerReview.objects.exists()


def test_low_ratings_open_one_review_and_repeats_add_none(employer, make_user):
    turn_on(make_user("admin", "Administrator"))
    rate(employer, 2, 2, 2)
    assert services.check_employer_reviews(timezone.localdate())["opened"] == 1
    assert services.check_employer_reviews(timezone.localdate())["opened"] == 0
    r = EmployerReview.objects.get()
    assert r.status == "open" and "low_average" in r.reasons and r.ratings_count == 3
    assert AuditEvent.objects.filter(action="employer.review_opened").count() == 1


def test_good_ratings_open_nothing_and_the_employer_is_untouched(employer, make_user):
    turn_on(make_user("admin", "Administrator"))
    rate(employer, 5, 4, 5)
    assert services.check_employer_reviews(timezone.localdate())["opened"] == 0
    rate(employer, 1, 1, 1, 1, 1, 1)
    services.check_employer_reviews(timezone.localdate())
    employer.refresh_from_db()
    assert employer.status == "active" and employer.archived_at is None


def test_the_command_reports(employer, make_user, capsys):
    call_command("check_employer_reviews")
    assert "off" in capsys.readouterr().out
    turn_on(make_user("admin", "Administrator"))
    call_command("check_employer_reviews")
    assert "checked 1 employers, opened 0" in capsys.readouterr().out


def test_an_administrator_decides_with_a_reason_and_it_closes(employer, make_user):
    admin = make_user("admin", "Administrator")
    turn_on(admin)
    rate(employer, 1, 1, 1)
    services.check_employer_reviews(timezone.localdate())
    c = api(admin)
    rows = c.get("/api/v1/employers/reviews?status=open").json()["results"]
    assert len(rows) == 1 and rows[0]["employer"] == "Acme"
    url = f"/api/v1/employers/reviews/{rows[0]['id']}/decision"
    post = lambda b: c.post(url, b, content_type="application/json")  # noqa: E731
    assert post({"outcome": "monitor", "reason": ""}).status_code == 400
    assert post({"outcome": "suspend", "reason": "x"}).status_code == 400
    r = post({"outcome": "monitor", "reason": "Keep an eye on it"})
    assert r.status_code == 200 and r.json()["status"] == "closed"
    assert r.json()["decided_by"] != ""
    assert post({"outcome": "ignore", "reason": "again"}).status_code == 409  # never edited
    assert AuditEvent.objects.filter(action="employer.review_decided").count() == 1
    # A later check may open a fresh review; the closed one stays as history.
    services.check_employer_reviews(timezone.localdate())
    assert EmployerReview.objects.count() == 2
    assert EmployerReview.objects.filter(status="closed").count() == 1


def test_the_queue_needs_the_review_permission(employer, make_user):
    for role in ("Placement officer", "Data steward"):
        c = api(make_user(f"u-{role}", role))
        assert c.get("/api/v1/employers/reviews").status_code == 403


def test_notes_are_hidden_without_the_notes_permission(employer, make_user):
    rate(employer, 4, note="Private detail")
    admin = api(make_user("admin", "Administrator"))
    row = admin.get(f"/api/v1/employers/{employer.pk}/feedback").json()["results"][0]
    assert row["note"] == "Private detail" and row["note_hidden"] is False
    viewer = api(make_user("viewer", "Manager"))
    resp = viewer.get(f"/api/v1/employers/{employer.pk}/feedback")
    assert resp.status_code == 200
    row = resp.json()["results"][0]
    assert row["note"] == "" and row["note_hidden"] is True


def test_the_employer_portal_never_sees_ratings_or_notes(employer, make_user):
    rate(employer, 1, note="Private detail")
    clients = [api(make_user(f"e-{n}", n)) for n in ("Company admin", "Employer viewer")]
    for c in clients:
        for url in (
            f"/api/v1/employers/{employer.pk}/feedback",
            "/api/v1/employers/reviews",
            "/api/v1/employers/feedback-criteria",
        ):
            assert c.get(url).status_code in (401, 403)
