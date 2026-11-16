"""The optional profile photo on a CV.

The upload is checked, cropped to a square and re-encoded as a small JPEG, which also drops any
camera data (location, device) it carried. It is stored in the database and served only through
authenticated endpoints, never as a public file."""

from io import BytesIO

from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.audit import services as audit

from .models import Participant, ParticipantPhoto

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000  # refuse decompression bombs before decoding
SIZE = 400
ALLOWED = {"JPEG", "PNG", "WEBP"}


class PhotoError(ValueError):
    def __init__(self, message, field="photo"):
        super().__init__(message)
        self.field = field


def _clean(raw: bytes) -> bytes:
    if not raw:
        raise PhotoError("Choose a photo to upload.")
    if len(raw) > MAX_BYTES:
        raise PhotoError("The photo is larger than 5 MB.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        probe = Image.open(BytesIO(raw))
        if probe.format not in ALLOWED:
            raise PhotoError("Use a JPG, PNG or WebP photo.")
        probe.verify()  # structure check; the image must be reopened to read it
        img = Image.open(BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img.load()
    except PhotoError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise PhotoError("That file is not a readable photo.") from None
    img = ImageOps.fit(img.convert("RGB"), (SIZE, SIZE), Image.LANCZOS)
    out = BytesIO()
    img.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


@transaction.atomic
def save(*, actor, p: Participant, raw: bytes) -> None:
    content = _clean(raw)
    ParticipantPhoto.objects.update_or_create(participant=p, defaults={"content": content})
    audit.record(
        actor=actor,
        action="participant.photo_set",
        object_type="participant",
        object_id=p.pk,
        after={"bytes": len(content)},
    )


def get(p: Participant) -> bytes | None:
    row = ParticipantPhoto.objects.filter(participant=p).only("content").first()
    return bytes(row.content) if row else None


def has(p: Participant) -> bool:
    return ParticipantPhoto.objects.filter(participant=p).exists()


@transaction.atomic
def remove(*, actor, p: Participant) -> None:
    deleted, _ = ParticipantPhoto.objects.filter(participant=p).delete()
    if deleted:
        audit.record(
            actor=actor,
            action="participant.photo_removed",
            object_type="participant",
            object_id=p.pk,
            after={},
        )
