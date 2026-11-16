"""CV endpoints for staff: the CV document, the PDF download and the photo.

Same rules as the rest of the profile: record scope applies (outside it is a 404), viewing needs
``participants.view_profile`` and changing the photo needs ``participants.edit``. Contact details
appear only for staff who also hold ``participants.view_contact``."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api import access
from apps.api.access import HasPermission
from apps.api.downloads import pdf_response, photo_response, read_photo_upload

from . import services
from .profile_views import EDIT, PROFILE, _participant

CONTACT = "participants.view_contact"


class CvView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PROFILE}

    @extend_schema(operation_id="participants_cv_get", responses={200: dict})
    def get(self, request, pk):
        p = _participant(request, pk)
        return Response(
            services.build_cv(p, include_contact=access.has_permission(request.user, CONTACT))
        )


class CvPdfView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PROFILE}

    @extend_schema(operation_id="participants_cv_pdf", responses={200: bytes})
    def get(self, request, pk):
        p = _participant(request, pk)
        data, name = services.cv_pdf(
            actor=request.user, p=p, include_contact=access.has_permission(request.user, CONTACT)
        )
        return pdf_response(data, name)


class PhotoView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": PROFILE, "POST": EDIT, "DELETE": EDIT}
    parser_classes = [MultiPartParser]

    @extend_schema(operation_id="participants_photo_get", responses={200: bytes})
    def get(self, request, pk):
        return photo_response(services.get_photo(_participant(request, pk)))

    @extend_schema(
        operation_id="participants_photo_post",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"photo": {"type": "string", "format": "binary"}},
            }
        },
        responses={204: None},
    )
    def post(self, request, pk):
        p = _participant(request, pk)
        try:
            services.save_photo(actor=request.user, p=p, raw=read_photo_upload(request))
        except services.PhotoError as exc:
            raise serializers.ValidationError({exc.field: [str(exc)]}) from exc
        return Response(status=204)

    @extend_schema(operation_id="participants_photo_delete", responses={204: None})
    def delete(self, request, pk):
        services.remove_photo(actor=request.user, p=_participant(request, pk))
        return Response(status=204)
