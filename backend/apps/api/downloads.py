"""Responses for files that carry personal data (a CV PDF, a profile photo).

Never cached, never sniffed, only ever returned to a signed-in caller by the view that uses them."""

from django.http import HttpResponse
from rest_framework import serializers

PHOTO_MAX_BYTES = 5 * 1024 * 1024
LOGO_MAX_BYTES = 2 * 1024 * 1024


def pdf_response(data: bytes, name: str) -> HttpResponse:
    resp = HttpResponse(data, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    resp["Cache-Control"] = "no-store, private"
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Access-Control-Expose-Headers"] = "Content-Disposition"
    return resp


def photo_response(data: bytes | None) -> HttpResponse:
    resp = (
        HttpResponse(status=404) if data is None else HttpResponse(data, content_type="image/jpeg")
    )
    resp["Cache-Control"] = "no-store, private"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


def read_photo_upload(request) -> bytes:
    upload = request.FILES.get("photo")
    if upload is None:
        raise serializers.ValidationError({"photo": ["Choose a photo to upload."]})
    if upload.size > PHOTO_MAX_BYTES:
        raise serializers.ValidationError({"photo": ["The photo is larger than 5 MB."]})
    return upload.read()


def logo_response(found: tuple[bytes, str] | None) -> HttpResponse:
    """A company logo: ``(bytes, content type)`` from the employers service, or 404."""
    resp = (
        HttpResponse(status=404) if found is None else HttpResponse(found[0], content_type=found[1])
    )
    resp["Cache-Control"] = "private, no-cache"  # the page adds ?v=<version> to see a new logo
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


def read_logo_upload(request) -> bytes:
    upload = request.FILES.get("logo")
    if upload is None:
        raise serializers.ValidationError({"logo": ["Choose a logo to upload."]})
    if upload.size > LOGO_MAX_BYTES:
        raise serializers.ValidationError({"logo": ["The logo is larger than 2 MB."]})
    return upload.read()
