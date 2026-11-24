"""CV of a youth: document, PDF download, photo, privacy and access. Synthetic data."""

import re
from datetime import date
from io import BytesIO

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import Client
from PIL import Image
from reportlab import rl_config

from apps.audit.models import AuditEvent
from apps.configuration.models import County, QualificationLevel, Sector, Skill
from apps.identity import services as identity
from apps.identity.models import Role
from apps.participants import cv as cv_module
from apps.participants.models import (
    Participant,
    ParticipantContact,
    ParticipantPhoto,
    ParticipantResidence,
)
from apps.portal import services as portal

PASSWORD = "a-much-longer-passphrase-9"  # noqa: S105 (test value)
SECRET_ID = "12345678"  # noqa: S105 (stands for a national id; it is never stored in a CV field)
PHONE, EMAIL = "0712345678", "samuel.kamau@example.org"


@pytest.fixture(autouse=True)
def _plain_pdf(monkeypatch):
    """Uncompressed PDFs so a test can read the text that was drawn."""
    cache.clear()
    monkeypatch.setattr(rl_config, "pageCompression", 0)


def api(user=None):
    c = Client()
    if user:
        c.force_login(user)
    return c


def pdf_text(data: bytes) -> str:
    return " ".join(
        m.replace("\\(", "(").replace("\\)", ")")
        for m in re.findall(r"\((.*?)\) Tj", data.decode("latin-1"))
    )


def pdf_pages(data: bytes) -> int:
    return len(re.findall(rb"/Type /Page\b(?!s)", data))


def jpeg(size=(800, 600), colour="navy", fmt="JPEG") -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, colour).save(buf, fmt)
    return buf.getvalue()


@pytest.fixture
def world(db, make_user):
    p = Participant.objects.create(
        full_name_source="Samuel Kamau",
        given_name="Samuel",
        other_names="Kamau",
        date_of_birth=date(2001, 4, 9),
        origin_county=County.objects.first(),
    )
    ParticipantContact.objects.create(participant=p, kind="phone", value=PHONE, is_primary=True)
    ParticipantContact.objects.create(participant=p, kind="email", value=EMAIL, is_primary=True)
    ParticipantResidence.objects.create(
        participant=p, county=County.objects.first(), sub_county_source="Westlands"
    )
    steward = make_user("steward", "Data steward")
    return {
        "p": p,
        "steward": steward,
        "level": QualificationLevel.objects.get(code="QL05"),
        "skill": Skill.objects.get(code="SK-FOOD"),
        "sector": Sector.objects.create(code="S1", name="Hospitality"),
        "profile": f"/api/v1/participants/{p.pk}/profile",
        "cv": f"/api/v1/participants/{p.pk}/cv",
        "pdf": f"/api/v1/participants/{p.pk}/cv.pdf",
        "photo": f"/api/v1/participants/{p.pk}/photo",
    }


def save_profile(w, body):
    r = api(w["steward"]).put(w["profile"], body, content_type="application/json")
    assert r.status_code == 200, r.content
    return r.json()


def full_profile(w):
    return {
        "qualifications": [
            {
                "level_id": str(w["level"].pk),
                "title": "Diploma in Food Production",
                "institution": "Nairobi Technical Institute",
                "field_of_study": "Culinary arts",
                "start_year": 2019,
                "year_awarded": 2021,
            },
            {
                "level_id": str(w["level"].pk),
                "title": "Certificate in Bakery",
                "institution": "Coast Polytechnic",
                "start_year": 2024,
                "currently_studying": True,
            },
        ],
        "skills": [{"skill_id": str(w["skill"].pk), "proficiency": 3}],
        "experience": [
            {
                "role_title": "Line Cook",
                "employer_name": "Savannah Hotel",
                "employment_type": "full_time",
                "start_date": "2021-02-01",
                "end_date": "2022-06-30",
                "responsibilities": "Prepared the lunch menu\nKept the station clean",
                "achievements": "Cut waste by a fifth",
            },
            {
                "role_title": "Sous Chef",
                "employer_name": "Lakeview Lodge",
                "start_date": "2022-09-01",
                "is_current": True,
                "responsibilities": "Ran the evening kitchen",
            },
        ],
        "certifications": [{"name": "Food Hygiene", "issuer": "KEBS", "year_obtained": 2022}],
        "practical": [
            {
                "organisation": "Community Kitchen",
                "role": "Volunteer cook",
                "kind": "volunteering",
                "start_date": "2020-01-01",
                "end_date": "2020-12-01",
                "description": "Weekend meals",
            }
        ],
        "languages": [
            {"language": "English", "proficiency": "fluent"},
            {"language": "Kiswahili", "proficiency": "native"},
        ],
        "readiness": {
            "summary": "A reliable cook with four years of kitchen experience.",
            "preferred_roles": ["Chef de partie"],
            "interest_sector_ids": [str(w["sector"].pk)],
            "preferred_county_ids": [str(County.objects.first().pk)],
            "willing_to_relocate": True,
            "available_from": "2026-12-01",
            "work_patterns": ["full_time"],
        },
    }


# ---- the document ------------------------------------------------------------------------------


def test_cv_orders_entries_most_recent_first(world):
    save_profile(world, full_profile(world))
    doc = api(world["steward"]).get(world["cv"]).json()
    assert [e["title"] for e in doc["experience"]] == ["Sous Chef", "Line Cook"]
    assert doc["experience"][0]["period"].endswith("Present")
    assert [q["course"] for q in doc["education"]] == [
        "Certificate in Bakery",
        "Diploma in Food Production",
    ]
    assert doc["education"][0]["period"] == "2024 - Present"
    assert doc["name"] == "Samuel Kamau"
    assert doc["contact"]["phone"] == PHONE and doc["contact"]["location"].startswith("Westlands")


def test_cv_holds_no_private_or_internal_data(world):
    save_profile(world, full_profile(world))
    raw = api(world["steward"]).get(world["cv"]).content.decode()
    for banned in (
        "date_of_birth",
        "2001-04-09",
        "national",
        "gender",
        "score",
        "verified",
        "source",
    ):
        assert banned not in raw
    assert str(world["p"].pk) not in raw
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", raw)


def test_work_experience_dates_give_the_months_and_end_date_after_start_is_required(world):
    save_profile(world, full_profile(world))
    months = api(world["steward"]).get(world["profile"]).json()["experience"]
    assert 16 in {m["months"] for m in months}  # Feb 2021 to Jun 2022 = 16
    bad = api(world["steward"]).put(
        world["profile"],
        {"experience": [{"role_title": "X", "start_date": "2022-01-01", "end_date": "2021-01-01"}]},
        content_type="application/json",
    )
    assert bad.status_code == 400


def test_experience_needs_dates_or_months(world):
    r = api(world["steward"]).put(
        world["profile"],
        {"experience": [{"role_title": "Cook"}]},
        content_type="application/json",
    )
    assert r.status_code == 400
    ok = api(world["steward"]).put(
        world["profile"],
        {"experience": [{"role_title": "Cook", "months": 6}]},
        content_type="application/json",
    )
    assert ok.status_code == 200


def test_readiness_write_changes_only_what_is_sent(world):
    save_profile(world, full_profile(world))
    save_profile(world, {"readiness": {"summary": "New summary."}})
    ready = api(world["steward"]).get(world["profile"]).json()["readiness"]
    assert ready["summary"] == "New summary."
    assert ready["preferred_roles"] == ["Chef de partie"]
    assert ready["interest_sectors"] == ["Hospitality"] and ready["willing_to_relocate"] is True


def test_input_validation(world):
    c = api(world["steward"])

    def put(body):
        return c.put(world["profile"], body, content_type="application/json")

    assert put({"readiness": {"summary": "x" * 601}}).status_code == 400
    assert put({"practical": [{"organisation": "Org", "kind": "nonsense"}]}).status_code == 400
    assert (
        put(
            {
                "qualifications": [
                    {"level_id": str(world["level"].pk), "start_year": 2023, "year_awarded": 2020}
                ]
            }
        ).status_code
        == 400
    )
    assert put({"languages": [{"language": "English"}, {"language": "english"}]}).status_code == 400
    assert put({"certifications": [{"name": ""}]}).status_code == 400
    assert (
        put(
            {"readiness": {"preferred_county_ids": ["00000000-0000-0000-0000-000000000000"]}}
        ).status_code
        == 400
    )


def test_completeness_counts_essentials_only(world):
    empty = cv_module.build(world["p"])["completeness"]
    assert empty["percent"] == 25  # the contact details already on the record
    assert {m["key"] for m in empty["missing"]} == {"summary", "education", "skills"}
    save_profile(world, full_profile(world))
    done = cv_module.build(world["p"])["completeness"]
    assert done["percent"] == 100 and done["missing"] == []
    # No work experience never lowers it.
    p2 = Participant.objects.create(full_name_source="No Work")
    ParticipantContact.objects.create(participant=p2, kind="phone", value="0700000000")
    assert cv_module.build(p2)["completeness"]["percent"] == 25


def test_no_formal_work_experience_flag_is_shown(world):
    save_profile(world, {"readiness": {"no_work_experience": True}})
    doc = cv_module.build(world["p"])
    assert doc["experience"] == [] and doc["no_work_experience"] is True
    assert "No formal work experience" in pdf_text(api(world["steward"]).get(world["pdf"]).content)


# ---- the PDF -----------------------------------------------------------------------------------


def test_pdf_download_has_name_headers_and_current_content(world):
    save_profile(world, full_profile(world))
    r = api(world["steward"]).get(world["pdf"])
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert 'filename="Samuel_Kamau_CV.pdf"' in r["Content-Disposition"]
    assert "no-store" in r["Cache-Control"]
    text = pdf_text(r.content)
    for expected in (
        "Samuel Kamau",
        "Savannah Hotel",
        "Food Hygiene",
        "Kiswahili (Native or bilingual)",
        PHONE,
        EMAIL,
    ):
        assert expected in text
    assert AuditEvent.objects.filter(action="participant.cv_downloaded").exists()
    # A change that was just saved is in the next download.
    save_profile(world, {"readiness": {"summary": "Freshly edited summary."}})
    assert "Freshly edited summary." in pdf_text(api(world["steward"]).get(world["pdf"]).content)


def test_pdf_leaves_out_empty_sections_and_private_data(world):
    r = api(world["steward"]).get(world["pdf"])
    text = pdf_text(r.content)
    for heading in (
        "WORK EXPERIENCE",
        "EDUCATION",
        "SKILLS",
        "CERTIFICATIONS",
        "LANGUAGES",
        "PROFESSIONAL SUMMARY",
    ):
        assert heading not in text
    # The PDF's own creation/modification timestamps can contain "2001" (e.g. 23:20:01).
    raw = re.sub(r"/(Creation|Mod)Date \(D:[^)]*\)", "", r.content.decode("latin-1"))
    for private in ("2001", "04-09", "Gender", "score", str(world["p"].pk)):
        assert private not in raw


def test_pdf_paginates_long_content_without_losing_anything(world):
    body = full_profile(world)
    body["experience"] = [
        {
            "role_title": f"Role {i:02d}",
            "employer_name": f"Employer {i:02d}",
            "start_date": "2010-01-01",
            "end_date": "2011-01-01",
            "responsibilities": "\n".join(f"Duty {i}-{j} carried out daily" for j in range(8)),
        }
        for i in range(25)
    ]
    save_profile(world, body)
    data = api(world["steward"]).get(world["pdf"]).content
    assert pdf_pages(data) >= 3
    text = pdf_text(data)
    assert all(f"Role {i:02d}" in text for i in range(25))
    assert "Page 1 of" in text and f"Page {pdf_pages(data)} of {pdf_pages(data)}" in text


def test_pdf_filename_is_safe_for_any_name():
    assert cv_module.filename("Samuel Kamau") == "Samuel_Kamau_CV.pdf"
    assert cv_module.filename('Amina "O\'Neil"/..\\x') == "Amina_O_Neil_x_CV.pdf"
    assert cv_module.filename("Ñandú Ωmega") == "Nandu_mega_CV.pdf"
    assert cv_module.filename("***") == "CV.pdf"


def test_markup_in_text_is_drawn_as_text(world):
    save_profile(world, {"readiness": {"summary": "I like <b>bold</b> & <script>x</script>"}})
    r = api(world["steward"]).get(world["pdf"])
    assert r.status_code == 200 and "< b > bold < /b >" in pdf_text(r.content)


# ---- photo -------------------------------------------------------------------------------------


def upload(c, url, data, name="me.jpg"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return c.post(url, {"photo": SimpleUploadedFile(name, data, content_type="image/jpeg")})


def test_photo_is_cropped_square_stripped_and_served_only_when_signed_in(world):
    c = api(world["steward"])
    assert upload(c, world["photo"], jpeg()).status_code == 204
    served = c.get(world["photo"])
    assert served.status_code == 200 and served["Content-Type"] == "image/jpeg"
    assert Image.open(BytesIO(served.content)).size == (400, 400)
    assert api().get(world["photo"]).status_code in (401, 403)
    doc = c.get(world["cv"]).json()
    assert doc["has_photo"] is True
    assert c.get(world["pdf"]).content.count(b"/Subtype /Image") == 1
    assert c.delete(world["photo"]).status_code == 204
    assert c.get(world["photo"]).status_code == 404


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image at all",
        b"GIF89a" + b"0" * 50,
        jpeg(fmt="BMP"),
        b"x" * (5 * 1024 * 1024 + 1),
    ],
)
def test_bad_photo_uploads_are_refused(world, data):
    r = upload(api(world["steward"]), world["photo"], data)
    assert r.status_code == 400 and ParticipantPhoto.objects.count() == 0


def test_a_broken_stored_photo_does_not_stop_the_download(world):
    ParticipantPhoto.objects.create(participant=world["p"], content=b"garbage")
    assert api(world["steward"]).get(world["pdf"]).status_code == 200


# ---- access ------------------------------------------------------------------------------------


def test_staff_outside_scope_get_404_and_anonymous_is_refused(world, make_user):
    out = make_user("outsider", "Placement officer")  # assigned scope, nothing assigned
    for key in ("cv", "pdf", "photo"):
        assert api(out).get(world[key]).status_code == 404
        assert api().get(world[key]).status_code in (401, 403)


def test_contact_needs_the_contact_permission(world, make_user):
    role = identity.create_role(
        actor=None, name="Profile only", permissions=["participants.view_profile"], scope_mode="all"
    )
    user = make_user("viewer")
    identity.assign_role(actor=None, user=user, role=Role.objects.get(pk=role.pk))
    doc = api(user).get(world["cv"]).json()
    assert doc["contact"]["phone"] == "" and doc["contact"]["email"] == ""
    assert PHONE not in pdf_text(api(user).get(world["pdf"]).content)


def test_photo_changes_need_the_edit_permission(world, make_user):
    role = identity.create_role(
        actor=None, name="Read only", permissions=["participants.view_profile"], scope_mode="all"
    )
    user = make_user("reader")
    identity.assign_role(actor=None, user=user, role=Role.objects.get(pk=role.pk))
    assert upload(api(user), world["photo"], jpeg()).status_code == 403
    assert api(user).delete(world["photo"]).status_code == 403


# ---- the youth's own CV ------------------------------------------------------------------------


def activate(world):
    c = api(world["steward"])
    c.post(
        f"/api/v1/participants/{world['p'].pk}/invite",
        {"email": EMAIL},
        content_type="application/json",
    )
    token = mail.outbox[-1].body.split("#token=")[1].split()[0]
    api().post(
        "/api/v1/youth/activate",
        {"token": token, "password": PASSWORD},
        content_type="application/json",
    )
    return api(User.objects.get(username=EMAIL))


def test_youth_downloads_their_own_cv_only_after_consent(world):
    save_profile(world, full_profile(world))
    youth = activate(world)
    assert youth.get("/api/v1/youth/cv").status_code == 400
    assert youth.get("/api/v1/youth/cv.pdf").status_code == 400
    youth.post(
        "/api/v1/youth/consent",
        {"version": portal.CONSENT_VERSION},
        content_type="application/json",
    )
    doc = youth.get("/api/v1/youth/cv").json()
    assert doc["name"] == "Samuel Kamau" and doc["completeness"]["percent"] == 100
    pdf = youth.get("/api/v1/youth/cv.pdf")
    assert pdf.status_code == 200 and "Samuel_Kamau_CV.pdf" in pdf["Content-Disposition"]
    assert "Savannah Hotel" in pdf_text(pdf.content)


def test_youth_photo_and_isolation_between_youth(world):
    youth = activate(world)
    youth.post(
        "/api/v1/youth/consent",
        {"version": portal.CONSENT_VERSION},
        content_type="application/json",
    )
    assert upload(youth, "/api/v1/youth/photo", jpeg()).status_code == 204
    assert youth.get("/api/v1/youth/photo").status_code == 200
    # Youth reach no staff route, so they cannot fetch another person's CV or photo.
    other = Participant.objects.create(full_name_source="Other Person")
    assert youth.get(f"/api/v1/participants/{other.pk}/cv").status_code == 403
    assert youth.get(f"/api/v1/participants/{world['p'].pk}/cv.pdf").status_code == 403
    assert youth.delete("/api/v1/youth/photo").status_code == 204
    assert youth.get("/api/v1/youth/photo").status_code == 404


def test_youth_cv_edit_flows_into_the_pdf(world):
    youth = activate(world)
    youth.post(
        "/api/v1/youth/consent",
        {"version": portal.CONSENT_VERSION},
        content_type="application/json",
    )
    r = youth.put(
        "/api/v1/youth/profile",
        {
            "readiness": {"summary": "Written by me."},
            "languages": [{"language": "English", "proficiency": "fluent"}],
        },
        content_type="application/json",
    )
    assert r.status_code == 200, r.content
    assert "Written by me." in pdf_text(youth.get("/api/v1/youth/cv.pdf").content)
