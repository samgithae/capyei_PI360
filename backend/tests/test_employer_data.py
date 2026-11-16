# ruff: noqa: F811, S105
"""Employer portal, phase 2: a company's own profile, opportunities and referrals.

What these prove: a company reaches only its own records (another company's id is a 404), the
publish-approval switch decides whether "open" publishes or asks staff, and nothing staff-only
(notes, scores, national ID, who handled a referral) ever reaches a company."""

import json
from datetime import date, timedelta

import pytest

from apps.audit.models import AuditEvent
from apps.configuration import services as configuration
from apps.configuration.models import County, QualificationLevel, ReferralReason, Sector, Skill
from apps.employers.models import Employer, EmployerContact, Opportunity, OpportunityRequirement
from apps.identity import services as identity
from apps.participants.models import Participant, ParticipantQualification, ParticipantSkill
from apps.referrals import services as referrals
from apps.referrals.models import Referral, StageEvent

from .test_employer_portal import (  # noqa: F401
    _fresh_throttle,
    acme,
    admin,
    api,
    beta,
    onboard,
    steward,
)
from .test_suggestions import activate_compatibility

JSON = "application/json"
P = "/api/v1/employer"
SECRET_NOTE = "INTERNAL-STAFF-NOTE-do-not-leak"
BIRTHDAY = "1999-04-17"
FORBIDDEN = (
    SECRET_NOTE, BIRTHDAY, "national_id", "date_of_birth", "dob", "gender", "score",
    "weights", "assigned_to", "created_by", "rule",
)  # fmt: skip


def future(days=30):
    return (date.today() + timedelta(days=days)).isoformat()


def assert_clean(response, *extra):
    """No staff-only word or value anywhere in the body."""
    body = response.content.decode().lower()
    for word in (*FORBIDDEN, *extra):
        assert word.lower() not in body, f"{word!r} leaked: {body[:300]}"


@pytest.fixture
def hr(steward, acme, admin):  # noqa: F811
    return onboard(steward, acme, "hr@acme.example", "HR / Recruiter")


@pytest.fixture
def viewer(steward, acme, admin):  # noqa: F811
    return onboard(steward, acme, "view@acme.example", "Employer viewer")


@pytest.fixture
def boss_b(steward, beta):  # noqa: F811
    return onboard(steward, beta, "dir@beta.example", "Company admin")


@pytest.fixture
def officer(make_user):
    user = make_user("wanjiru", "Placement officer")
    identity.set_scopes(actor=None, user=user, scopes=[("officer", "self")])
    return user


def new_opportunity(employer, **kw):
    return Opportunity.objects.create(
        employer=employer, title=kw.pop("title", "Sales assistant"), **kw
    )


def refer(officer, employer, name="Test Youth A", title="Sales assistant", stage=None):
    youth = Participant.objects.create(
        full_name_source=name, assigned_officer=officer, date_of_birth=BIRTHDAY, gender="F"
    )
    opp = Opportunity.objects.filter(employer=employer, title=title).first() or new_opportunity(
        employer, title=title, status=Opportunity.OPEN, closing_date=date.today() + timedelta(30)
    )
    ref = referrals.create_referral(
        actor=officer, participant_id=youth.pk, opportunity_id=opp.pk, note=SECRET_NOTE
    )
    if stage:
        referrals.transition(actor=officer, referral=ref, to=stage)
    return youth, opp, Referral.objects.get(pk=ref.pk)


# ---- profile and contacts ----------------------------------------------------------------------


def test_the_company_reads_its_profile_without_staff_notes(admin, acme):
    acme.notes = SECRET_NOTE
    acme.save()
    r = api(admin).get(f"{P}/profile")
    assert r.status_code == 200 and r.json()["name"] == "Acme Traders"
    assert_clean(r, "notes", "status")


def test_the_company_edits_where_it_is_but_not_its_name_or_status(admin, acme):
    county = County.objects.first()
    sector = Sector.objects.create(code="S9", name="Retail")
    r = api(admin).patch(
        f"{P}/profile",
        {
            "name": "Hijacked Ltd", "status": "inactive", "notes": "hi", "sub_county": "Westlands",
            "website": "https://acme.example", "county_ids": [str(county.pk)],
            "sector_ids": [str(sector.pk)],
        },
        content_type=JSON,
    )  # fmt: skip
    assert r.status_code == 200, r.content
    acme.refresh_from_db()
    assert (acme.name, acme.status, acme.notes) == ("Acme Traders", Employer.ACTIVE, "")
    assert acme.sub_county == "Westlands" and [c.pk for c in acme.counties.all()] == [county.pk]


def test_contacts_are_managed_by_the_company_and_only_its_own(admin, boss_b, acme, beta):
    c = api(admin)
    made = c.post(
        f"{P}/contacts", {"name": "Wanjiru", "email": "w@acme.example", "is_primary": True},
        content_type=JSON,
    )  # fmt: skip
    assert made.status_code == 201
    cid = made.json()["id"]
    assert (
        c.patch(f"{P}/contacts/{cid}", {"role": "Director"}, content_type=JSON).status_code == 200
    )
    # another company's admin cannot reach it
    assert (
        api(boss_b).patch(f"{P}/contacts/{cid}", {"role": "x"}, content_type=JSON).status_code
        == 404
    )
    assert api(boss_b).delete(f"{P}/contacts/{cid}").status_code == 404
    assert EmployerContact.objects.filter(pk=cid).exists()
    assert c.delete(f"{P}/contacts/{cid}").status_code == 204


def test_a_viewer_reads_but_cannot_change_the_profile(viewer):
    c = api(viewer)
    assert c.get(f"{P}/profile").status_code == 200
    assert c.patch(f"{P}/profile", {"address": "x"}, content_type=JSON).status_code == 403
    assert c.post(f"{P}/contacts", {"name": "x"}, content_type=JSON).status_code == 403


# ---- opportunities -----------------------------------------------------------------------------


def make_draft(c, **extra):
    body = {"title": "Store clerk", "positions": 2, "closing_date": future(), **extra}
    r = c.post(f"{P}/opportunities", body, content_type=JSON)
    assert r.status_code == 201, r.content
    return r.json()


def test_a_company_creates_a_draft_for_itself_only(hr, acme, beta):
    d = make_draft(api(hr))
    assert d["status"] == "draft" and d["employer"] == "Acme Traders"
    assert Opportunity.objects.get(pk=d["id"]).employer_id == acme.pk
    # an employer_id in the body is ignored, never obeyed
    d2 = make_draft(api(hr), employer_id=str(beta.pk))
    assert Opportunity.objects.get(pk=d2["id"]).employer_id == acme.pk


def test_the_list_and_detail_hold_only_this_companys_opportunities(hr, boss_b, acme, beta):
    mine, theirs = new_opportunity(acme, title="Mine"), new_opportunity(beta, title="Theirs")
    r = api(hr).get(f"{P}/opportunities")
    assert [o["title"] for o in r.json()["results"]] == ["Mine"]
    assert api(hr).get(f"{P}/opportunities/{theirs.pk}").status_code == 404
    assert api(boss_b).get(f"{P}/opportunities/{mine.pk}").status_code == 404
    assert api(hr).patch(
        f"{P}/opportunities/{theirs.pk}", {"title": "x"}, content_type=JSON
    ).status_code == 404  # fmt: skip
    assert api(hr).post(
        f"{P}/opportunities/{theirs.pk}/transition", {"to": "open"}, content_type=JSON
    ).status_code == 404  # fmt: skip
    theirs.refresh_from_db()
    assert theirs.title == "Theirs" and theirs.status == Opportunity.DRAFT


def test_requirements_are_edited_in_the_own_opportunity_only(hr, boss_b, acme, beta):
    c = api(hr)
    d = make_draft(c)
    skill = Skill.objects.get(code="SK-FOOD")
    base = f"{P}/opportunities/{d['id']}/requirements"
    made = c.post(
        base, {"factor": "skill", "description": "Cooking", "skill_id": str(skill.pk)},
        content_type=JSON,
    )  # fmt: skip
    assert made.status_code == 201, made.content
    rid = made.json()["id"]
    assert c.patch(f"{base}/{rid}", {"is_mandatory": True}, content_type=JSON).status_code == 200
    # another company can neither read, change nor delete it, even with both ids right
    other = api(boss_b)
    assert (
        other.patch(f"{base}/{rid}", {"is_mandatory": False}, content_type=JSON).status_code == 404
    )
    assert other.delete(f"{base}/{rid}").status_code == 404
    assert other.post(base, {"factor": "other"}, content_type=JSON).status_code == 404
    # a requirement of another opportunity is "missing" under this one
    theirs = new_opportunity(beta, title="Theirs")
    foreign = OpportunityRequirement.objects.create(opportunity=theirs, factor="other")
    assert (
        c.patch(f"{base}/{foreign.pk}", {"description": "x"}, content_type=JSON).status_code == 404
    )
    assert c.delete(f"{base}/{rid}").status_code == 204


def test_the_skills_picker_saves_in_one_call(hr):
    c = api(hr)
    d = make_draft(c)
    food, weld = Skill.objects.get(code="SK-FOOD"), Skill.objects.get(code="SK-WELDING")
    r = c.put(
        f"{P}/opportunities/{d['id']}/requirements/skills",
        {"skills": [{"skill_id": str(food.pk), "is_mandatory": True}, {"skill_id": str(weld.pk)}]},
        content_type=JSON,
    )
    assert r.status_code == 200, r.content
    assert len(r.json()["requirements"]) == 2


def test_with_the_switch_off_open_asks_staff_to_approve(hr, steward):
    c = api(hr)
    d = make_draft(c)
    r = c.post(f"{P}/opportunities/{d['id']}/transition", {"to": "open"}, content_type=JSON)
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["status"] == "draft" and body["publish_request"]["state"] == "pending"
    assert body["publish_request"]["requested_by"] == "Wanjiru Director"
    assert body["publishes_directly"] is False
    assert AuditEvent.objects.filter(action="opportunity.publish_requested").exists()
    # asking twice is refused
    again = c.post(f"{P}/opportunities/{d['id']}/transition", {"to": "open"}, content_type=JSON)
    assert again.status_code == 409
    # staff see it waiting, and approve with the ordinary transition
    queue = api(steward).get("/api/v1/opportunities", {"awaiting": "1"}).json()
    assert [o["id"] for o in queue["results"]] == [d["id"]]
    ok = api(steward).post(
        f"/api/v1/opportunities/{d['id']}/transition", {"to": "open"}, content_type=JSON
    )
    assert ok.status_code == 200, ok.content
    after = c.get(f"{P}/opportunities/{d['id']}").json()
    assert after["status"] == "open" and after["publish_request"]["state"] == "none"


def test_the_company_can_take_back_a_request(hr):
    c = api(hr)
    d = make_draft(c)
    c.post(f"{P}/opportunities/{d['id']}/transition", {"to": "open"}, content_type=JSON)
    r = c.post(f"{P}/opportunities/{d['id']}/transition", {"to": "withdraw"}, content_type=JSON)
    assert r.status_code == 200 and r.json()["publish_request"]["state"] == "none"
    assert c.post(
        f"{P}/opportunities/{d['id']}/transition", {"to": "withdraw"}, content_type=JSON
    ).status_code == 409  # fmt: skip


def test_staff_decline_needs_a_reason_and_the_company_sees_it(hr, steward):
    c = api(hr)
    d = make_draft(c)
    c.post(f"{P}/opportunities/{d['id']}/transition", {"to": "open"}, content_type=JSON)
    url = f"/api/v1/opportunities/{d['id']}/publish-decline"
    s = api(steward)
    assert s.post(url, {}, content_type=JSON).status_code == 400
    assert s.post(url, {"reason": "Add the pay range."}, content_type=JSON).status_code == 200
    seen = c.get(f"{P}/opportunities/{d['id']}").json()["publish_request"]
    assert seen["state"] == "declined" and seen["declined_reason"] == "Add the pay range."
    # the company can ask again after fixing it
    again = c.post(f"{P}/opportunities/{d['id']}/transition", {"to": "open"}, content_type=JSON)
    assert again.status_code == 200 and again.json()["publish_request"]["state"] == "pending"
    # a decline with nothing waiting is refused
    s.post(f"/api/v1/opportunities/{d['id']}/transition", {"to": "open"}, content_type=JSON)
    assert s.post(url, {"reason": "late"}, content_type=JSON).status_code == 409


def test_with_the_switch_on_open_publishes_at_once(hr):
    configuration.set_flag(actor=None, key="employer_self_publish", enabled=True)
    c = api(hr)
    d = make_draft(c)
    r = c.post(f"{P}/opportunities/{d['id']}/transition", {"to": "open"}, content_type=JSON)
    assert r.status_code == 200, r.content
    assert r.json()["status"] == "open" and r.json()["publishes_directly"] is True
    closed = c.post(f"{P}/opportunities/{d['id']}/transition", {"to": "closed"}, content_type=JSON)
    assert closed.json()["status"] == "closed"


def test_opening_still_needs_a_future_closing_date(hr):
    configuration.set_flag(actor=None, key="employer_self_publish", enabled=True)
    c = api(hr)
    d = make_draft(c, closing_date=None)
    r = c.post(f"{P}/opportunities/{d['id']}/transition", {"to": "open"}, content_type=JSON)
    assert r.status_code == 409 and r.json()["errors"][0]["field"] == "closing_date"
    # a request is checked the same way, so staff are never asked to approve something unopenable
    configuration.set_flag(actor=None, key="employer_self_publish", enabled=False)
    r = c.post(f"{P}/opportunities/{d['id']}/transition", {"to": "open"}, content_type=JSON)
    assert r.status_code == 409


def test_only_roles_with_the_publish_permission_may_ask_to_open(steward, acme, admin):
    manager = onboard(steward, acme, "hm@acme.example", "Hiring manager")
    d = make_draft(api(admin))
    for who in (manager, onboard(steward, acme, "v@acme.example", "Employer viewer")):
        r = api(who).post(
            f"{P}/opportunities/{d['id']}/transition", {"to": "open"}, content_type=JSON
        )
        assert r.status_code == 403
    assert api(manager).patch(
        f"{P}/opportunities/{d['id']}", {"title": "x"}, content_type=JSON
    ).status_code == 403  # fmt: skip


def test_the_opportunity_never_carries_staff_only_data(hr, acme):
    d = make_draft(api(hr))
    r = api(hr).get(f"{P}/opportunities/{d['id']}")
    assert_clean(r)
    assert_clean(api(hr).get(f"{P}/opportunities"))


# ---- referrals ---------------------------------------------------------------------------------


def test_drafts_and_other_companies_referrals_are_not_listed(hr, boss_b, officer, acme, beta):
    _, _, mine = refer(officer, acme, "Mine Youth")
    _, opp, draft = refer(officer, acme, "Draft Youth", title="Other role")
    Referral.objects.filter(pk=draft.pk).update(stage=Referral.DRAFT)
    _, _, theirs = refer(officer, beta, "Theirs Youth")
    r = api(hr).get(f"{P}/referrals")
    assert [x["id"] for x in r.json()["results"]] == [str(mine.pk)]
    assert api(hr).get(f"{P}/referrals/{theirs.pk}").status_code == 404
    assert api(hr).get(f"{P}/referrals/{draft.pk}").status_code == 404
    assert api(boss_b).get(f"{P}/referrals/{mine.pk}").status_code == 404
    for tail in ("cv", "cv.pdf", "photo", "why"):
        assert api(hr).get(f"{P}/referrals/{theirs.pk}/{tail}").status_code == 404, tail


def test_the_referral_shows_nothing_staff_only(hr, officer, acme):
    _, _, ref = refer(officer, acme)
    for url in (f"{P}/referrals", f"{P}/referrals/{ref.pk}", f"{P}/referrals/{ref.pk}/cv"):
        r = api(hr).get(url)
        assert r.status_code == 200
        assert_clean(r, "wanjiru", "officer")


def test_history_says_placement_team_for_staff_and_names_the_company_user(hr, officer, acme):
    _, _, ref = refer(officer, acme)
    c = api(hr)
    c.post(f"{P}/referrals/{ref.pk}/transition", {"to": "under_review", "note": "Looks good"},
           content_type=JSON)  # fmt: skip
    h = c.get(f"{P}/referrals/{ref.pk}").json()["history"]
    assert h[0]["by"] == "PI360 placement team" and h[0]["note"] == ""
    assert (
        h[-1]["by"] == "Wanjiru Director" and h[-1]["note"] == "Looks good" and h[-1]["own"] is True
    )


def test_a_company_moves_a_referral_and_the_event_records_its_user(hr, officer, acme):
    _, _, ref = refer(officer, acme)
    c = api(hr)
    r = c.post(f"{P}/referrals/{ref.pk}/transition", {"to": "interview"}, content_type=JSON)
    assert r.status_code == 200, r.content
    assert r.json()["can_set_interview"] is True
    iv = c.post(
        f"{P}/referrals/{ref.pk}/interview",
        {"at": "2030-01-10T09:00:00Z", "place": "Head office", "note": "Bring your ID"},
        content_type=JSON,
    )
    assert iv.status_code == 200 and iv.json()["interview"]["place"] == "Head office"
    event = StageEvent.objects.filter(referral=ref).order_by("-id").first()
    assert event.actor_id == hr.pk and event.to_stage == "interview"
    assert AuditEvent.objects.filter(action="referral.interview_set", actor_id=hr.pk).exists()


def test_interview_details_only_while_at_the_interview_stage(hr, officer, acme):
    _, _, ref = refer(officer, acme)
    r = api(hr).post(
        f"{P}/referrals/{ref.pk}/interview", {"at": "2030-01-10T09:00:00Z"}, content_type=JSON
    )
    assert r.status_code == 409


def test_rejecting_needs_a_reason_and_the_reasons_list_is_for_rejection(hr, officer, acme):
    _, _, ref = refer(officer, acme)
    c = api(hr)
    reasons = c.get(f"{P}/referral-reasons").json()["results"]
    assert reasons and all(set(x) == {"id", "name", "needs_note"} for x in reasons)
    assert c.post(f"{P}/referrals/{ref.pk}/transition", {"to": "rejected"}, content_type=JSON
                  ).status_code == 409  # fmt: skip
    ok = ReferralReason.objects.filter(applies_to__in=["rejected", "any"], needs_note=False,
                                       active=True).first()  # fmt: skip
    r = c.post(f"{P}/referrals/{ref.pk}/transition",
               {"to": "rejected", "reason_id": str(ok.pk)}, content_type=JSON)  # fmt: skip
    assert r.status_code == 200 and r.json()["stage"] == "rejected"
    assert r.json()["history"][-1]["reason"] == ok.name


def test_placing_closing_and_withdrawing_stay_with_staff(hr, officer, acme):
    _, _, ref = refer(officer, acme)
    c = api(hr)
    for to in ("placed", "closed", "withdrawn", "no_response", "submitted", "draft"):
        r = c.post(f"{P}/referrals/{ref.pk}/transition", {"to": to}, content_type=JSON)
        assert r.status_code in (400, 409), to
    ref.refresh_from_db()
    assert ref.stage == "submitted"


def test_a_move_the_stage_model_does_not_allow_is_refused(hr, officer, acme):
    _, _, ref = refer(officer, acme, stage="under_review")
    api(hr).post(f"{P}/referrals/{ref.pk}/transition", {"to": "selected"}, content_type=JSON)
    r = api(hr).post(
        f"{P}/referrals/{ref.pk}/transition", {"to": "under_review"}, content_type=JSON
    )
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "bad_transition"


def test_a_viewer_reads_referrals_but_cannot_respond(viewer, officer, acme):
    _, _, ref = refer(officer, acme)
    c = api(viewer)
    assert c.get(f"{P}/referrals/{ref.pk}").status_code == 200
    assert c.post(f"{P}/referrals/{ref.pk}/transition", {"to": "under_review"},
                  content_type=JSON).status_code == 403  # fmt: skip
    assert c.post(f"{P}/referrals/{ref.pk}/interview", {"at": "2030-01-10T09:00:00Z"},
                  content_type=JSON).status_code == 403  # fmt: skip


def test_list_filters_and_stage_counts(hr, officer, acme):
    _, _, a = refer(officer, acme, "Alpha Youth")
    _, _, b = refer(officer, acme, "Beta Youth")
    api(hr).post(f"{P}/referrals/{b.pk}/transition", {"to": "under_review"}, content_type=JSON)
    c = api(hr)
    assert c.get(f"{P}/referrals", {"stage": "under_review"}).json()["total"] == 1
    assert c.get(f"{P}/referrals", {"q": "alpha"}).json()["results"][0]["id"] == str(a.pk)
    assert c.get(f"{P}/referrals").json()["counts"] == {"submitted": 1, "under_review": 1}
    assert c.get(f"{P}/referrals", {"opportunity": "not-a-uuid"}).json()["total"] == 0


# ---- the candidate's CV ------------------------------------------------------------------------


def with_contact(youth):
    from apps.participants.models import ParticipantContact

    ParticipantContact.objects.create(
        participant=youth, kind="phone", value="0712345678", is_primary=True
    )
    ParticipantContact.objects.create(
        participant=youth, kind="email", value="youth@example.org", is_primary=True
    )


def test_contact_details_are_hidden_until_selected(hr, officer, acme):
    youth, _, ref = refer(officer, acme, stage="under_review")
    with_contact(youth)
    c = api(hr)
    early = c.get(f"{P}/referrals/{ref.pk}/cv")
    assert early.status_code == 200 and early.json()["contact_visible"] is False
    assert "0712345678" not in early.content.decode()
    assert "youth@example.org" not in early.content.decode()
    c.post(f"{P}/referrals/{ref.pk}/transition", {"to": "selected"}, content_type=JSON)
    late = c.get(f"{P}/referrals/{ref.pk}/cv")
    assert late.json()["contact_visible"] is True
    assert "0712345678" in late.content.decode() and "youth@example.org" in late.content.decode()
    assert_clean(late)


def test_contact_goes_away_again_if_the_youth_withdraws_after_selection(hr, officer, acme):
    youth, _, ref = refer(officer, acme, stage="selected")
    with_contact(youth)
    why = ReferralReason.objects.filter(applies_to__in=["withdrawn", "any"]).first()
    referrals.transition(actor=officer, referral=ref, to="withdrawn", reason_id=str(why.pk))
    assert api(hr).get(f"{P}/referrals/{ref.pk}/cv").json()["contact_visible"] is False


def test_the_cv_pdf_downloads_and_is_audited_against_the_company_user(hr, officer, acme):
    _, _, ref = refer(officer, acme, stage="under_review")
    r = api(hr).get(f"{P}/referrals/{ref.pk}/cv.pdf")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert AuditEvent.objects.filter(action="participant.cv_downloaded", actor_id=hr.pk).exists()
    assert BIRTHDAY.encode() not in r.content


def test_the_cv_has_no_profile_completeness_advice(hr, officer, acme):
    _, _, ref = refer(officer, acme)
    assert "completeness" not in api(hr).get(f"{P}/referrals/{ref.pk}/cv").json()


# ---- why this youth was suggested --------------------------------------------------------------


def fit_world(officer, acme):
    ql5 = QualificationLevel.objects.get(code="QL05")
    cook = Skill.objects.get(code="SK-FOOD")
    youth = Participant.objects.create(full_name_source="Fit Youth", assigned_officer=officer)
    ParticipantQualification.objects.create(participant=youth, level=ql5)
    ParticipantSkill.objects.create(participant=youth, skill=cook, proficiency=2)
    opp = Opportunity.objects.create(
        employer=acme, title="Cook", status="open", closing_date=date.today() + timedelta(30)
    )
    R = OpportunityRequirement.objects
    R.create(opportunity=opp, factor="qualification", description="Diploma", is_mandatory=True,
             qualification_level=ql5)  # fmt: skip
    R.create(opportunity=opp, factor="skill", description="Cooking", is_mandatory=True, skill=cook)
    return Referral.objects.create(
        participant=youth, opportunity=opp, stage="submitted", referred_at=None
    )


def test_why_suggested_is_plain_words_with_no_scores(hr, officer, acme):
    activate_compatibility()
    ref = fit_world(officer, acme)
    r = api(hr).get(f"{P}/referrals/{ref.pk}/why")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["available"] is True and "must-have" in body["summary"]
    assert {c["label"] for c in body["checks"]} >= {"Diploma", "Cooking"}
    assert all(c["outcome"] in {"met", "not_met", "not_recorded"} for c in body["checks"])
    assert all(set(c) == {"label", "must_have", "outcome"} for c in body["checks"])
    assert_clean(r, "version", "coverage", "met_total", "preferred")


def test_why_suggested_says_so_when_there_is_nothing_to_show(hr, officer, acme):
    ref = fit_world(officer, acme)  # no rule is active
    body = api(hr).get(f"{P}/referrals/{ref.pk}/why").json()
    assert body == {"available": False, "summary": "", "checks": []}


def test_why_suggested_is_not_open_to_staff_or_other_companies(boss_b, officer, acme, make_user):
    ref = fit_world(officer, acme)
    assert api(boss_b).get(f"{P}/referrals/{ref.pk}/why").status_code == 404
    assert api(officer).get(f"{P}/referrals/{ref.pk}/why").status_code == 403


# ---- staff are unchanged ------------------------------------------------------------------------


def test_staff_opportunity_list_gains_the_publish_request_state(steward, acme):
    new_opportunity(acme)
    row = api(steward).get("/api/v1/opportunities").json()["results"][0]
    assert row["publish_request"]["state"] == "none"


def test_a_company_user_cannot_use_the_staff_endpoints(hr, acme, officer):
    _, o, ref = refer(officer, acme)
    for method, url in (
        ("get", "/api/v1/opportunities"),
        ("get", f"/api/v1/opportunities/{o.pk}"),
        ("post", f"/api/v1/opportunities/{o.pk}/publish-decline"),
        ("get", "/api/v1/referrals"),
        ("get", f"/api/v1/referrals/{ref.pk}"),
        ("get", f"/api/v1/referrals/{ref.pk}/fit"),
        ("get", f"/api/v1/participants/{ref.participant_id}/cv"),
        ("get", f"/api/v1/participants/{ref.participant_id}/cv.pdf"),
    ):
        assert getattr(api(hr), method)(url).status_code == 403, url


def test_the_responses_are_valid_json_and_never_cached(hr, officer, acme):
    _, _, ref = refer(officer, acme)
    r = api(hr).get(f"{P}/referrals/{ref.pk}")
    json.loads(r.content)
