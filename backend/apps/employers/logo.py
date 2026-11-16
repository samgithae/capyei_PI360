"""A company's logo.

The upload is checked, shrunk to fit a small box and re-encoded, which also drops any camera or
editor data it carried. Pictures with see-through areas stay PNG so they keep them; others become
JPEG. It is stored in the database and served only through authenticated endpoints. SVG is refused
on purpose: it can carry scripts."""

from io import BytesIO

from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.audit import services as audit

from .models import Employer, EmployerLogo

MAX_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 40_000_000  # refuse decompression bombs before decoding
BOX = 512
ALLOWED = {"JPEG", "PNG", "WEBP"}


class LogoError(ValueError):
    def __init__(self, message, field="logo"):
        super().__init__(message)
        self.field = field


def _clean(raw: bytes) -> tuple[bytes, str]:
    if not raw:
        raise LogoError("Choose a logo to upload.")
    if len(raw) > MAX_BYTES:
        raise LogoError("The logo is larger than 2 MB.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        probe = Image.open(BytesIO(raw))
        if probe.format not in ALLOWED:
            raise LogoError("Use a PNG, JPG or WebP image.")
        probe.verify()  # structure check; the image must be reopened to read it
        img = Image.open(BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img.load()
    except LogoError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise LogoError("That file is not a readable image.") from None
    img.thumbnail((BOX, BOX), Image.LANCZOS)  # keeps the shape, never enlarges
    out = BytesIO()
    if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        img.convert("RGBA").save(out, "PNG", optimize=True)
        return out.getvalue(), "image/png"
    img.convert("RGB").save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue(), "image/jpeg"


@transaction.atomic
def save(*, actor, employer: Employer, raw: bytes) -> None:
    content, content_type = _clean(raw)
    EmployerLogo.objects.update_or_create(
        employer=employer, defaults={"content": content, "content_type": content_type}
    )
    audit.record(
        actor=actor,
        action="employer.logo_set",
        object_type="employer",
        object_id=employer.pk,
        after={"bytes": len(content)},
    )


def get(employer_id) -> tuple[bytes, str] | None:
    row = EmployerLogo.objects.filter(employer_id=employer_id).first()
    return (bytes(row.content), row.content_type) if row else None


def version(employer_id) -> str | None:
    """Changes whenever the logo does, so a page can ask for the new picture. None if no logo."""
    at = (
        EmployerLogo.objects.filter(employer_id=employer_id)
        .values_list("updated_at", flat=True)
        .first()
    )
    return str(int(at.timestamp() * 1000)) if at else None


@transaction.atomic
def remove(*, actor, employer: Employer) -> None:
    deleted, _ = EmployerLogo.objects.filter(employer=employer).delete()
    if deleted:
        audit.record(
            actor=actor,
            action="employer.logo_removed",
            object_type="employer",
            object_id=employer.pk,
            after={},
        )
