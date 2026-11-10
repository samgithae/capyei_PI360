"""RFC 9457 (formerly 7807) problem responses for every API error (doc 04 CMP-02).

Shape: {type, title, status, detail, instance, request_id, errors?}
``errors`` lists field errors as {field, message, code} for validation failures.
Content type: application/problem+json.
"""

from django.http import JsonResponse
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

CONTENT_TYPE = "application/problem+json"
TYPE_BASE = "https://pi360.capyei.org/problems/"  # stable identifiers, not fetched

TITLES = {
    400: "Invalid request",
    401: "Not signed in",
    403: "Not allowed",
    404: "Not found",
    405: "Method not allowed",
    406: "Not acceptable",
    409: "Conflict",
    415: "Unsupported media type",
    429: "Too many requests",
    500: "Server error",
}


def problem(status_code, *, code, detail="", instance="", request_id=None, errors=None):
    body = {
        "type": TYPE_BASE + code.replace("_", "-"),
        "title": TITLES.get(status_code, "Error"),
        "status": status_code,
        "detail": str(detail),
        "instance": instance,
        "request_id": request_id,
    }
    if errors:
        body["errors"] = errors
    return body


def _flatten(detail, prefix=""):
    """DRF ValidationError detail -> [{field, message, code}]."""
    out = []
    if isinstance(detail, dict):
        for key, value in detail.items():
            if isinstance(key, int):  # list item errors arrive keyed by index
                field = f"{prefix}[{key}]"
            else:
                field = f"{prefix}.{key}" if prefix else str(key)
            out += _flatten(value, "" if key == "non_field_errors" else field)
    elif isinstance(detail, list):
        for i, value in enumerate(detail):
            nested = isinstance(value, dict | list)
            out += _flatten(value, f"{prefix}[{i}]" if nested else prefix)
    else:
        out.append(
            {
                "field": prefix or None,
                "message": str(detail),
                "code": getattr(detail, "code", "invalid"),
            }
        )
    return out


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    request = context.get("request")
    request_id = getattr(request, "request_id", None)
    instance = request.path if request is not None else ""
    if response is None:
        # Unhandled: let Django log it, then return a problem without internals.
        return None
    errors = None
    if isinstance(exc, exceptions.ValidationError):
        code, detail = "validation_error", "One or more fields are invalid."
        errors = _flatten(exc.detail)
    elif isinstance(exc, exceptions.APIException):
        code = exc.default_code
        detail = response.data.get("detail", "") if isinstance(response.data, dict) else ""
    else:  # Http404, PermissionDenied converted by DRF
        code, detail = ("not_found" if response.status_code == 404 else "permission_denied"), ""
    body = problem(
        response.status_code,
        code=code,
        detail=detail,
        instance=instance,
        request_id=request_id,
        errors=errors,
    )
    out = Response(body, status=response.status_code, headers=dict(response.items()))
    out.content_type = CONTENT_TYPE
    return out


def _django_problem(request, status_code, code, detail):
    body = problem(
        status_code,
        code=code,
        detail=detail,
        instance=request.path,
        request_id=getattr(request, "request_id", None),
    )
    return JsonResponse(body, status=status_code, content_type=CONTENT_TYPE)


def not_found(request, exception=None):
    return _django_problem(request, status.HTTP_404_NOT_FOUND, "not_found", "No such endpoint.")


def server_error(request):
    return _django_problem(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "server_error",
        "Something went wrong. Quote the request ID when reporting it.",
    )
