# ruff: noqa: F811, S105
"""Employer people: a contact and a portal account are one person, on one list.

What these prove: inviting someone adds them to the contact list (or links the contact already
there), the list shows each person once with their access, edits to the contact reach the sign-in
and the sign-in e-mail cannot be changed from the contact, a person who can sign in cannot be
removed by accident, and old accounts were matched to contacts by e-mail when this arrived."""

import importlib

from django.apps import apps as django_apps
from django.contrib.auth.models import User

from apps.employer_portal.models import EmployerMember
from apps.employers.models import EmployerContact

from .test_employer_data import boss_b, hr, viewer  # noqa: F401
from .test_employer_portal import (  # noqa: F401
    JSON,
    _fresh_throttle,
    acme,
    activate,
    admin,
    api,
    beta,
    company_invite,
    role_id,
    staff_invite,
    steward,
)


def people(user, employer):
    r = api(user).get(f"/api/v1/employers/{employer.pk}/people")
    assert r.status_code == 200, r.content
    return r.json()["people"]


def add_contact(user, employer, **fields):
    body = {"name": "Akinyi Hiring", "email": "akinyi@acme.example", **fields}
    r = api(user).post(f"/api/v1/employers/{employer.pk}/contacts", body, content_type=JSON)
    assert r.status_code == 201, r.content
    return r.json()


def test_inviting_a_new_person_adds_them_to_the_contact_list(steward, acme):
    row = staff_invite(steward, acme, phone="0700 111 222", is_primary=True).json()
    [person] = people(steward, acme)
    assert person["name"] == "Wanjiru Director" and person["email"] == "dir@acme.example"
    assert person["phone"] == "0700 111 222" and person["is_primary"] is True
    assert person["access"]["state"] == "pending" and person["access"]["id"] == row["id"]
    assert row["contact_id"] == person["id"]
    assert EmployerContact.objects.filter(employer=acme).count() == 1


def test_an_invite_uses_the_contact_already_listed_with_that_address(steward, acme):
    listed = add_contact(steward, acme, role="Recruiter", phone="0711")
    staff_invite(steward, acme, email="AKINYI@acme.example", role="HR / Recruiter")
    [person] = people(steward, acme)
    assert person["id"] == listed["id"] and person["access"] is not None
    assert person["phone"] == "0711" and person["role"] == "Recruiter"  # kept, not blanked
    assert person["name"] == "Wanjiru Director"  # the invitation's name


def test_access_can_be_given_to_a_listed_person_by_id(steward, acme):
    listed = add_contact(steward, acme)
    r = staff_invite(
        steward, acme, email=listed["email"], role="Hiring manager", contact_id=listed["id"]
    )
    assert r.status_code == 201 and r.json()["contact_id"] == listed["id"]
    [person] = people(steward, acme)
    assert person["access"]["roles"] == ["Hiring manager"]


def test_a_person_without_access_is_listed_with_no_access(steward, acme):
    add_contact(steward, acme)
    [person] = people(steward, acme)
    assert person["access"] is None


def test_another_companys_person_cannot_be_given_access(steward, acme, beta):
    theirs = add_contact(steward, beta)
    r = staff_invite(steward, acme, contact_id=theirs["id"])
    assert r.status_code == 400 and "no such person" in r.content.decode().lower()
    assert people(steward, acme) == []


def test_a_person_with_an_account_cannot_be_invited_again(steward, acme, admin):
    [person] = people(steward, acme)
    r = staff_invite(steward, acme, email="other@acme.example", contact_id=person["id"])
    assert r.status_code == 400 and "already has an account" in r.content.decode()


def test_editing_the_contact_updates_the_signed_in_name_and_title(steward, acme, admin):
    [person] = people(steward, acme)
    r = api(steward).patch(
        f"/api/v1/employers/{acme.pk}/contacts/{person['id']}",
        {"name": "Wanjiru M. Director", "role": "Head of People"},
        content_type=JSON,
    )
    assert r.status_code == 200
    member = EmployerMember.objects.get(user=admin)
    assert (member.full_name, member.job_title) == ("Wanjiru M. Director", "Head of People")
    [after] = people(steward, acme)
    assert after["access"]["name"] == "Wanjiru M. Director"


def test_the_sign_in_address_cannot_be_changed_from_the_contact(steward, acme, admin):
    [person] = people(steward, acme)
    api(steward).patch(
        f"/api/v1/employers/{acme.pk}/contacts/{person['id']}",
        {"email": "someone.else@acme.example"},
        content_type=JSON,
    )
    assert people(steward, acme)[0]["email"] == "dir@acme.example"
    admin.refresh_from_db()
    assert admin.email == "dir@acme.example"


def test_the_company_editing_its_own_contact_reaches_the_sign_in_too(steward, acme, admin):
    [person] = people(steward, acme)
    r = api(admin).patch(
        f"/api/v1/employer/contacts/{person['id']}", {"name": "W. Director"}, content_type=JSON
    )
    assert r.status_code == 200
    assert EmployerMember.objects.get(user=admin).full_name == "W. Director"


def test_a_person_who_can_sign_in_cannot_be_removed(steward, acme, admin):
    [person] = people(steward, acme)
    r = api(steward).delete(f"/api/v1/employers/{acme.pk}/contacts/{person['id']}")
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "has_portal_access"
    assert len(people(steward, acme)) == 1
    own = api(admin).delete(f"/api/v1/employer/contacts/{person['id']}")
    assert own.status_code == 409


def test_withdrawing_an_invite_keeps_the_person_and_they_can_then_be_removed(steward, acme):
    row = staff_invite(steward, acme).json()
    gone = api(steward).delete(f"/api/v1/employers/{acme.pk}/users/{row['id']}")
    assert gone.status_code == 204
    [person] = people(steward, acme)
    assert person["access"] is None
    removed = api(steward).delete(f"/api/v1/employers/{acme.pk}/contacts/{person['id']}")
    assert removed.status_code == 204 and people(steward, acme) == []


def test_a_new_invite_after_a_withdrawal_reuses_the_same_person(steward, acme):
    row = staff_invite(steward, acme).json()
    api(steward).delete(f"/api/v1/employers/{acme.pk}/users/{row['id']}")
    staff_invite(steward, acme)
    [person] = people(steward, acme)
    assert person["access"]["state"] == "pending"
    assert EmployerContact.objects.filter(employer=acme).count() == 1


def test_the_company_team_page_invite_also_lists_the_person(steward, acme, admin):
    assert company_invite(admin).status_code == 201
    emails = {p["email"] for p in people(steward, acme)}
    assert emails == {"dir@acme.example", "hr@acme.example"}


def test_the_people_list_is_one_company_only_and_needs_the_permission(
    steward, acme, beta, make_user, admin
):
    add_contact(steward, beta, email="b@beta.example", name="Beta Person")
    assert [p["email"] for p in people(steward, acme)] == ["dir@acme.example"]
    youth = make_user("youth1", "Youth")
    assert api(youth).get(f"/api/v1/employers/{acme.pk}/people").status_code == 403
    assert api().get(f"/api/v1/employers/{acme.pk}/people").status_code in (401, 403)


def test_the_sign_in_still_works_after_the_contact_is_edited(steward, acme, admin):
    [person] = people(steward, acme)
    api(steward).patch(
        f"/api/v1/employers/{acme.pk}/contacts/{person['id']}",
        {"phone": "0722"},
        content_type=JSON,
    )
    assert User.objects.get(username="dir@acme.example").is_active


# ---- the company's own list ----------------------------------------------------------------


def own_people(user):
    r = api(user).get("/api/v1/employer/people")
    assert r.status_code == 200, r.content
    return r.json()


def test_the_company_admin_sees_each_person_once_with_their_access(acme, admin, hr):
    body = own_people(admin)
    assert body["can_access"] is True
    assert {p["email"] for p in body["people"]} == {"dir@acme.example", "hr@acme.example"}
    by_email = {p["email"]: p for p in body["people"]}
    assert by_email["hr@acme.example"]["access"]["roles"] == ["HR / Recruiter"]
    assert {r["name"] for r in body["roles"]} >= {"Company admin", "Employer viewer"}
    assert all(set(r) == {"id", "name", "description"} for r in body["roles"])


def test_someone_who_may_not_manage_the_team_sees_the_people_but_not_who_can_sign_in(
    acme, admin, hr, viewer
):
    for user in (hr, viewer):
        body = own_people(user)
        assert body["can_access"] is False and body["roles"] == []
        assert len(body["people"]) == 3
        assert all(p["access"] is None for p in body["people"])


def test_a_contact_without_an_account_is_listed_and_can_be_given_access(acme, admin):
    made = (
        api(admin)
        .post(
            "/api/v1/employer/contacts",
            {"name": "Otieno Ops", "email": "ops@acme.example"},
            content_type=JSON,
        )
        .json()
    )
    row = next(p for p in own_people(admin)["people"] if p["id"] == made["id"])
    assert row["access"] is None
    r = api(admin).post(
        "/api/v1/employer/staff",
        {
            "contact_id": made["id"],
            "email": "ops@acme.example",
            "full_name": "Otieno Ops",
            "role_id": role_id("Employer viewer"),
        },
        content_type=JSON,
    )
    assert r.status_code == 201
    row = next(p for p in own_people(admin)["people"] if p["id"] == made["id"])
    assert row["access"]["state"] == "pending"
    assert EmployerContact.objects.filter(employer=acme).count() == 2


def test_a_company_sees_only_its_own_people(acme, beta, admin, boss_b):
    assert [p["email"] for p in own_people(boss_b)["people"]] == ["dir@beta.example"]
    assert [p["email"] for p in own_people(admin)["people"]] == ["dir@acme.example"]


def test_the_company_people_list_needs_signing_in_and_an_employer_account(steward):
    assert api().get("/api/v1/employer/people").status_code in (401, 403)
    assert api(steward).get("/api/v1/employer/people").status_code == 403


# ---- the data migration --------------------------------------------------------------------


def test_existing_accounts_are_matched_to_contacts_by_email(steward, acme):
    """Accounts made before contacts and accounts were one list: match by e-mail (any case) and
    give each account with no contact a new one."""
    matched = EmployerContact.objects.create(
        employer=acme, name="Old Name", email="Dir@Acme.Example", phone="0700", is_primary=True
    )
    staff_invite(steward, acme, email="dir@acme.example")
    staff_invite(steward, acme, email="solo@acme.example")
    EmployerMember.objects.update(contact=None)
    EmployerContact.objects.exclude(pk=matched.pk).delete()

    migration = importlib.import_module("apps.employer_portal.migrations.0002_member_contact")
    migration.link_members(django_apps, None)

    by_email = {m.user.email: m for m in EmployerMember.objects.select_related("contact", "user")}
    assert by_email["dir@acme.example"].contact_id == matched.pk
    matched.refresh_from_db()
    assert matched.phone == "0700" and matched.is_primary is True  # nothing else lost
    assert matched.email == "dir@acme.example"
    solo = by_email["solo@acme.example"].contact
    assert solo is not None and solo.email == "solo@acme.example" and solo.employer_id == acme.pk
    assert EmployerContact.objects.filter(employer=acme).count() == 2
    assert role_id  # imported for the shared fixtures
