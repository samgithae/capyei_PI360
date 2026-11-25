"""Per-criterion scores on employer feedback (NEW-026) and their summary (NEW-027, Scenario 6).
The criteria list is working data while D-077 is open; these tests do not rely on its wording."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.employers import services as employers
from apps.employers.models import Employer, EmployerFeedback, FeedbackCriterion
from apps.intelligence import services

from .test_participants import world  # noqa: F401

pytestmark = pytest.mark.django_db


def api(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def employer(db):
    return Employer.objects.create(name="Acme")


def body(**kw):
    return {
        "party": "employer", "source": "call", "rating": 4,
        "given_on": timezone.localdate().isoformat(),
    } | kw  # fmt: skip


def post(c, employer, **kw):
    return c.post(
        f"/api/v1/employers/{employer.pk}/feedback", body(**kw), content_type="application/json"
    )


def evidence(employer):
    return services.employer_evidence(employer.pk, timezone.localdate())


def test_working_criteria_are_seeded_and_listed(make_user):
    rows = api(make_user("admin", "Administrator")).get("/api/v1/employers/feedback-criteria")
    assert {c["code"] for c in rows.json()["results"]} >= {"work-quality", "punctuality"}


def test_scores_are_saved_with_the_entry_and_listed(employer, make_user):
    c = api(make_user("admin", "Administrator"))
    r = post(c, employer, scores={"work-quality": 5, "punctuality": 3}, kind="placement")
    assert r.status_code == 201
    assert r.json()["scores"] == {"work-quality": 5, "punctuality": 3}
    ev = AuditEvent.objects.get(action="employer.feedback_added")
    assert ev.after["criteria_scored"] == 2


@pytest.mark.parametrize("scores", [{"work-quality": 0}, {"work-quality": 6}, {"nonsense": 3}])
def test_a_score_outside_1_to_5_or_for_an_unknown_criterion_is_refused(employer, make_user, scores):
    r = post(api(make_user("admin", "Administrator")), employer, scores=scores)
    assert r.status_code in (400, 409)
    assert not EmployerFeedback.objects.exists()


def test_a_switched_off_criterion_cannot_be_scored(employer, make_user):
    FeedbackCriterion.objects.filter(code="punctuality").update(active=False)
    r = post(api(make_user("admin", "Administrator")), employer, scores={"punctuality": 4})
    assert r.status_code in (400, 409)


def test_entries_without_scores_behave_as_before(employer, make_user):
    assert post(api(make_user("admin", "Administrator")), employer).status_code == 201
    row = EmployerFeedback.objects.get()
    assert row.kind == "general" and row.review_status == "included" and row.placement_id is None
    assert evidence(employer)["criteria"] == []


def add_scores(employer, n, score, code="work-quality"):
    for _ in range(n):
        employers.add_feedback(
            actor=None, employer=employer,
            data=body() | {"scores": {code: score}, "given_on": timezone.localdate()},
        )  # fmt: skip


def test_below_the_minimum_there_is_a_count_but_no_average(employer):
    add_scores(employer, 4, 5)  # the default minimum is 5
    c = evidence(employer)["criteria"][0]
    assert c["count"] == 4 and c["average"] is None and c["status"] == "insufficient"


def test_at_the_minimum_each_criterion_has_its_own_average_and_there_is_no_overall(employer):
    add_scores(employer, 3, 5)
    add_scores(employer, 2, 3)
    add_scores(employer, 5, 2, code="punctuality")
    out = evidence(employer)
    by = {c["code"]: c for c in out["criteria"]}
    assert by["work-quality"]["average"] == 4.2 and by["punctuality"]["average"] == 2.0
    assert "overall" not in str(out).lower().replace("overall_", "x")  # D-027: no composite


def test_left_out_entries_are_not_counted_and_the_reason_is_audited(employer, make_user):
    c = api(make_user("admin", "Administrator"))
    add_scores(employer, 5, 4)
    fb = EmployerFeedback.objects.first()
    url = f"/api/v1/employers/{employer.pk}/feedback/{fb.pk}/review"
    bad = c.post(url, {"status": "excluded"}, content_type="application/json")
    assert bad.status_code in (400, 409)
    ok = c.post(url, {"status": "excluded", "reason": "Duplicate"}, content_type="application/json")
    assert ok.status_code == 200
    crit = evidence(employer)["criteria"][0]
    assert crit["count"] == 4 and crit["average"] is None  # now under the minimum
    fb_ind = next(i for i in evidence(employer)["indicators"] if i["label"] == "Employer feedback")
    assert fb_ind["of"] == 4
    assert AuditEvent.objects.get(action="employer.feedback_review").reason == "Duplicate"


def test_old_scores_outside_the_period_are_not_counted(employer):
    employers.add_feedback(
        actor=None, employer=employer,
        data=body(given_on=timezone.localdate()) | {"scores": {"work-quality": 5}},
    )  # fmt: skip
    EmployerFeedback.objects.update(given_on=timezone.localdate() - timedelta(days=400))
    assert evidence(employer)["criteria"] == []
