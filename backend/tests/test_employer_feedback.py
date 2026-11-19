"""Officer-logged employer feedback (D-013): a stated source, a 1 to 5 rating, a minimum before
a percentage shows, and an audited removal."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.employers.models import Employer, EmployerFeedback
from apps.intelligence import services

from .test_participants import world  # noqa: F401


def api(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def employer(db):
    return Employer.objects.create(name="Acme")


def body(**kw):
    return {
        "party": "employer", "source": "call", "rating": 5,
        "note": "Happy with the intake", "given_on": timezone.localdate().isoformat(),
    } | kw  # fmt: skip


def log(employer, n, *, rating=5, days_ago=1):
    for _ in range(n):
        EmployerFeedback.objects.create(
            employer=employer, party="employer", source="call", rating=rating,
            given_on=timezone.localdate() - timedelta(days=days_ago),
        )  # fmt: skip


def indicator(employer_id):
    out = services.employer_evidence(employer_id, timezone.localdate())
    return next(i for i in out["indicators"] if i["label"] == "Employer feedback")


def test_an_officer_logs_feedback_and_it_is_listed_and_audited(employer, make_user):
    c = api(make_user("admin", "Administrator"))
    r = c.post(f"/api/v1/employers/{employer.pk}/feedback", body(), content_type="application/json")
    assert r.status_code == 201 and r.json()["source_label"] == "Phone call"
    rows = c.get(f"/api/v1/employers/{employer.pk}/feedback").json()["results"]
    assert [x["rating"] for x in rows] == [5]
    ev = AuditEvent.objects.get(action="employer.feedback_added")
    assert "Happy with the intake" not in str(ev.after)  # the note stays out of the audit trail


@pytest.mark.parametrize(
    "change",
    [
        {"rating": 0}, {"rating": 6}, {"source": ""}, {"source": "rumour"}, {"party": "boss"},
        {"given_on": (timezone.localdate() + timedelta(days=1)).isoformat()},
    ],
)  # fmt: skip
def test_unsourced_or_out_of_range_feedback_is_refused(employer, make_user, change):
    c = api(make_user("admin", "Administrator"))
    r = c.post(
        f"/api/v1/employers/{employer.pk}/feedback", body(**change), content_type="application/json"
    )
    assert r.status_code in (400, 409)
    assert not EmployerFeedback.objects.exists()


def test_removal_needs_a_reason_and_is_audited(employer, make_user):
    c = api(make_user("admin", "Administrator"))
    log(employer, 1)
    fb = EmployerFeedback.objects.get()
    url = f"/api/v1/employers/{employer.pk}/feedback/{fb.pk}"
    assert c.delete(url, {"reason": " "}, content_type="application/json").status_code in (400, 409)
    assert (
        c.delete(url, {"reason": "Wrong employer"}, content_type="application/json").status_code
        == 204
    )
    assert not EmployerFeedback.objects.exists()
    assert AuditEvent.objects.get(action="employer.feedback_removed").reason == "Wrong employer"


def test_no_feedback_says_no_data(employer):
    assert indicator(employer.pk)["status"] == "no_data"


def test_under_the_minimum_shows_counts_but_no_percentage(employer):
    log(employer, 3)
    log(employer, 1, rating=2)
    i = indicator(employer.pk)
    assert i["status"] == "insufficient" and i["percent"] is None
    assert i["text"] == "3 of 4 feedback entries were positive"


def test_enough_entries_show_a_percentage_and_the_settings_apply(employer):
    log(employer, 3, rating=4)
    log(employer, 2, rating=3)
    i = indicator(employer.pk)
    assert i["status"] == "shown" and i["percent"] == 60
    services.update_settings(
        actor=None, values={"employer.positive_rating": 3, "employer.min_feedback": 6}
    )
    i = indicator(employer.pk)
    assert i["status"] == "insufficient" and i["of"] == 5 and i["count"] == 5


def test_feedback_outside_the_period_is_not_counted(employer):
    log(employer, 5, days_ago=400)
    assert indicator(employer.pk)["status"] == "no_data"
