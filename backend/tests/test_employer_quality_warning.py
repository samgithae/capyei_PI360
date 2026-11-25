"""NEW-075: a quality warning beside suggestions. It never changes who is eligible or the order.
Synthetic data."""

from datetime import date

import pytest

from apps.employers.models import Employer, EmployerFeedback

from .test_suggestions import activate_compatibility, api, world  # noqa: F401


def rate(employer, *ratings):
    for r in ratings:
        EmployerFeedback.objects.create(
            employer=employer, party="employer", source="call", rating=r, given_on=date.today()
        )


@pytest.fixture
def admin(make_user):
    return api(make_user("admin", "Administrator"))


def test_no_ratings_no_warning(world, admin):  # noqa: F811
    activate_compatibility()
    q = admin.get(world["url"]).json()["employer_quality"]
    assert q["warning"] is False and q["note"] == ""


def test_low_average_with_enough_ratings_warns(world, admin):  # noqa: F811
    activate_compatibility()
    rate(world["o"].employer, 2, 2, 3)  # three ratings, average 2.3
    q = admin.get(world["url"]).json()["employer_quality"]
    assert q["warning"] is True and q["ratings"] == 3


def test_good_ratings_do_not_warn(world, admin):  # noqa: F811
    activate_compatibility()
    rate(world["o"].employer, 4, 5, 3)
    assert admin.get(world["url"]).json()["employer_quality"]["warning"] is False


def test_too_few_ratings_do_not_warn_unless_one_is_a_one(world, admin):  # noqa: F811
    activate_compatibility()
    rate(world["o"].employer, 2, 2)
    assert admin.get(world["url"]).json()["employer_quality"]["warning"] is False
    rate(world["o"].employer, 1)
    q = admin.get(world["url"]).json()["employer_quality"]
    assert q["warning"] is True and any("rating of 1" in r for r in q["reasons"])


def test_the_warning_changes_neither_eligibility_nor_order(world, admin):  # noqa: F811
    activate_compatibility()
    before = admin.get(world["url"]).json()
    rate(world["o"].employer, 1, 1, 1)
    after = admin.get(world["url"]).json()
    assert after["employer_quality"]["warning"] is True
    assert [(s["name"], s["group"], s["score"]) for s in after["suggestions"]] == [
        (s["name"], s["group"], s["score"]) for s in before["suggestions"]
    ]


def test_an_inactive_employer_gets_no_suggestions(world, admin):  # noqa: F811
    activate_compatibility()
    Employer.objects.filter(pk=world["o"].employer_id).update(status="inactive")
    body = admin.get(world["url"]).json()
    assert body["available"] is False and "Inactive" in body["reason"]
    assert "suggestions" not in body


def test_the_warning_carries_counts_never_comments(world, admin):  # noqa: F811
    activate_compatibility()
    EmployerFeedback.objects.create(
        employer=world["o"].employer, party="employer", source="call", rating=1,
        note="Private remark", given_on=date.today(),
    )  # fmt: skip
    assert "Private remark" not in admin.get(world["url"]).content.decode()
