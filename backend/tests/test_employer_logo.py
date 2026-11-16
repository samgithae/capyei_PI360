# ruff: noqa: F811, S105
"""Employer profile: a logo and a short description about the company.

What these prove: a company admin can set, replace and remove the logo and write a description,
the picture is checked, shrunk and re-encoded (SVG and other formats refused), it is served only
to signed-in people from that company, and one company never sees or changes another's."""

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.audit.models import AuditEvent
from apps.employers.models import EmployerLogo

from .test_employer_data import boss_b, hr, viewer  # noqa: F401
from .test_employer_portal import (  # noqa: F401
    JSON,
    _fresh_throttle,
    acme,
    admin,
    api,
    beta,
    steward,
)

LOGO = "/api/v1/employer/logo"
PROFILE = "/api/v1/employer/profile"


def picture(size=(900, 300), colour="navy", fmt="PNG", mode="RGB") -> bytes:
    buf = BytesIO()
    Image.new(mode, size, colour).save(buf, fmt)
    return buf.getvalue()


def upload(user, data, name="logo.png"):
    file = SimpleUploadedFile(name, data, content_type="image/png")
    return api(user).post(LOGO, {"logo": file})


def test_the_admin_sets_a_logo_and_it_is_shrunk_and_served(admin):
    r = upload(admin, picture())
    assert r.status_code == 200 and r.json()["logo_version"]
    served = api(admin).get(LOGO)
    assert served.status_code == 200 and served["Content-Type"] == "image/jpeg"
    assert served["X-Content-Type-Options"] == "nosniff"
    assert Image.open(BytesIO(served.content)).size == (512, 171)  # fits the box, same shape


def test_a_small_logo_is_not_enlarged_and_a_see_through_one_stays_png(admin):
    assert (
        upload(admin, picture(size=(64, 32), mode="RGBA", colour=(0, 0, 0, 0))).status_code == 200
    )
    served = api(admin).get(LOGO)
    assert served["Content-Type"] == "image/png"
    assert Image.open(BytesIO(served.content)).size == (64, 32)


def test_a_new_logo_replaces_the_old_one(admin, acme):
    first = upload(admin, picture()).json()["logo_version"]
    second = upload(admin, picture(colour="red")).json()["logo_version"]
    assert EmployerLogo.objects.filter(employer=acme).count() == 1
    assert first and second


def test_the_logo_can_be_removed(admin, acme):
    upload(admin, picture())
    r = api(admin).delete(LOGO)
    assert r.status_code == 200 and r.json()["logo_version"] is None
    assert api(admin).get(LOGO).status_code == 404 and not EmployerLogo.objects.exists()


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image at all",
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b"GIF89a" + b"0" * 50,
        picture(fmt="BMP"),
        b"x" * (2 * 1024 * 1024 + 1),
    ],
)
def test_bad_uploads_are_refused(admin, data):
    r = upload(admin, data)
    assert r.status_code == 400 and not EmployerLogo.objects.exists()


def test_a_request_with_no_file_is_refused(admin):
    assert api(admin).post(LOGO, {}).status_code == 400


def test_the_description_is_saved_and_shown(admin):
    text = "We build roads and bridges across the Coast."
    r = api(admin).patch(PROFILE, {"description": text}, content_type=JSON)
    assert r.status_code == 200 and r.json()["description"] == text
    assert api(admin).get(PROFILE).json()["description"] == text


def test_a_description_longer_than_600_characters_is_refused(admin):
    r = api(admin).patch(PROFILE, {"description": "x" * 601}, content_type=JSON)
    assert r.status_code == 400
    assert (
        api(admin).patch(PROFILE, {"description": "x" * 600}, content_type=JSON).status_code == 200
    )


def test_only_those_who_may_edit_the_profile_can_change_the_logo(admin, hr, viewer):
    upload(admin, picture())
    for user in (hr, viewer):
        assert upload(user, picture()).status_code == 403
        assert api(user).delete(LOGO).status_code == 403
        assert api(user).get(LOGO).status_code == 200  # everyone in the company sees it


def test_a_company_never_sees_or_changes_anothers_logo(admin, boss_b, acme, beta):
    upload(admin, picture())
    assert api(boss_b).get(LOGO).status_code == 404
    assert upload(boss_b, picture(colour="green")).status_code == 200
    assert EmployerLogo.objects.filter(employer=acme).count() == 1
    assert EmployerLogo.objects.filter(employer=beta).count() == 1
    assert api(boss_b).delete(LOGO).status_code == 200
    assert EmployerLogo.objects.filter(employer=acme).exists()


def test_the_logo_needs_signing_in_and_an_employer_account(steward):
    assert api().get(LOGO).status_code in (401, 403)
    assert api(steward).get(LOGO).status_code == 403


def test_changes_are_audited_without_the_picture(admin, acme):
    upload(admin, picture())
    api(admin).delete(LOGO)
    actions = set(
        AuditEvent.objects.filter(object_id=str(acme.pk)).values_list("action", flat=True)
    )
    assert {"employer.logo_set", "employer.logo_removed"} <= actions
