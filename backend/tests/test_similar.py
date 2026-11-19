"""Search and duplicate warnings (T-055, FR-37): near-duplicate check on create, tolerant search."""

import datetime

import pytest
from django.test import Client

from apps.configuration.models import County
from apps.participants.models import Participant, ParticipantContact, SourceIdentifier

URL = "/api/v1/participants"


def client_for(user):
    c = Client()
    c.force_login(user)
    return c


def add(name, phone="", dob=None, county=None):
    p = Participant.objects.create(
        full_name_source=name, gender="female", date_of_birth=dob, origin_county=county
    )
    if phone:
        ParticipantContact.objects.create(participant=p, kind="phone", value=phone, is_primary=True)
    return p


@pytest.fixture
def people(db):
    return {
        "john": add("John Kamau Mwangi", "0712 345 678", datetime.date(2001, 5, 4)),
        "mary": add("Mary Wanjiru", "+254 700 111 222"),
        "other": add("Zablon Otieno"),
    }


def check(c, **params):
    return c.get(f"{URL}/check-name", params).json()["matches"]


def codes(match):
    return [r["code"] for r in match["reasons"]]


def test_same_name_is_flagged(people, make_user):
    c = client_for(make_user("steward", "Data steward"))
    found = check(c, name="john kamau mwangi")
    assert [m["name"] for m in found] == ["John Kamau Mwangi"]
    assert codes(found[0]) == ["same_name"]


def test_reordered_and_misspelt_names_are_flagged(people, make_user):
    c = client_for(make_user("steward", "Data steward"))
    swapped = check(c, name="Mwangi John Kamau")
    assert codes(swapped[0]) == ["same_words"]
    typo = check(c, name="Jon Kamau Mwangi")
    assert [m["name"] for m in typo] == ["John Kamau Mwangi"]
    assert codes(typo[0]) == ["similar_name"]


def test_unrelated_and_short_names_are_not_flagged(people, make_user):
    c = client_for(make_user("steward", "Data steward"))
    assert check(c, name="Nobody Here") == []
    assert check(c, name="Jo") == []


def test_phone_and_birthdate_sharpen_a_partial_name(people, make_user):
    c = client_for(make_user("steward", "Data steward"))
    # a shared first name alone is not a duplicate
    assert check(c, name="John Otieno") == []
    # the same phone in another format, with a shared name part, is
    found = check(c, name="John Kamau", phone="+254712345678")
    assert [m["name"] for m in found] == ["John Kamau Mwangi"]
    assert "same_phone" in codes(found[0])
    # same date of birth and a close name
    found = check(c, name="John Kamau", dob="2001-05-04")
    assert "same_birthdate" in codes(found[0])
    # the same phone with an unrelated name is a family line, not a duplicate
    assert check(c, name="Zablon Otieno", phone="0712345678")[0]["name"] == "Zablon Otieno"
    assert check(c, name="Peter Njoroge", phone="0712345678") == []


def test_matches_never_reveal_the_phone_or_birthdate(people, make_user):
    c = client_for(make_user("steward", "Data steward"))
    body = c.get(
        f"{URL}/check-name", {"name": "John Kamau", "phone": "0712345678", "dob": "2001-05-04"}
    ).content.decode()
    assert "0712" not in body and "2001" not in body


def test_check_is_closed_to_roles_that_cannot_add_youth(people, make_user):
    analyst = client_for(make_user("analyst", "M&E analyst"))
    assert analyst.get(f"{URL}/check-name", {"name": "John Kamau"}).status_code == 403


def test_matches_say_who_to_tell_apart(db, make_user):
    kisumu = County.objects.get(code="01")
    add("Grace Atieno", county=kisumu)
    c = client_for(make_user("steward", "Data steward"))
    found = check(c, name="Grace Atieno")
    assert found[0]["county"] == kisumu.name
    assert found[0]["programmes"] == []


def test_search_matches_words_in_any_order_and_ids(people, make_user):
    SourceIdentifier.objects.create(
        participant=people["mary"], source="Go Blue", identifier="GB-0042"
    )
    c = client_for(make_user("steward", "Data steward"))
    body = c.get(URL, {"q": "mwangi john"}).json()
    assert [r["name"] for r in body["results"]] == ["John Kamau Mwangi"]
    assert body["similar_names"] is False
    assert [r["name"] for r in c.get(URL, {"q": "gb-0042"}).json()["results"]] == ["Mary Wanjiru"]


def test_search_falls_back_to_near_spellings(people, make_user):
    c = client_for(make_user("steward", "Data steward"))
    body = c.get(URL, {"q": "Jon Kamu"}).json()
    assert body["similar_names"] is True
    assert [r["name"] for r in body["results"]] == ["John Kamau Mwangi"]
    none = c.get(URL, {"q": "Qwertyuiop"}).json()
    assert none["total"] == 0 and none["similar_names"] is False


def test_search_is_scoped_to_what_the_caller_may_see(people, make_user):
    officer = make_user("officer", "Placement officer")
    body = client_for(officer).get(URL, {"q": "Jon Kamu"}).json()
    assert body["total"] == 0
