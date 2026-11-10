"""CMP-02 conventions and CMP-15 request IDs (T-032)."""

import json
import logging

import pytest
from django.urls import path
from rest_framework import serializers
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.platform.observability import JsonFormatter, RequestIdFilter


class _Echo(serializers.Serializer):
    name = serializers.CharField(max_length=5)
    items = serializers.ListField(child=serializers.IntegerField())


class _EchoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        _Echo(data=request.data).is_valid(raise_exception=True)
        return None


class _ThrottledView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        raise Throttled(wait=30)


class _PrivateView(APIView):
    """Uses the project defaults: session auth, signed-in users only."""

    def get(self, request):
        return None


class _BoomView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        raise RuntimeError("internal detail that must not leak")


urlpatterns = [
    path("api/v1/_echo", _EchoView.as_view()),
    path("api/v1/_throttled", _ThrottledView.as_view()),
    path("api/v1/_boom", _BoomView.as_view()),
    path("api/v1/_private", _PrivateView.as_view()),
]
handler404 = "apps.api.problems.not_found"
handler500 = "apps.api.problems.server_error"

PROBLEM_KEYS = {"type", "title", "status", "detail", "instance", "request_id"}


def assert_problem(res, status):
    assert res.status_code == status
    assert res["Content-Type"] == "application/problem+json"
    body = res.json()
    assert PROBLEM_KEYS <= body.keys()
    assert body["status"] == status
    assert body["request_id"] == res["X-Request-ID"]
    return body


@pytest.mark.urls(__name__)
def test_validation_error_is_a_problem_with_field_errors(client):
    res = client.post(
        "/api/v1/_echo", {"name": "too long", "items": ["x"]}, content_type="application/json"
    )
    body = assert_problem(res, 400)
    assert body["type"].endswith("/validation-error")
    assert body["instance"] == "/api/v1/_echo"
    fields = {e["field"] for e in body["errors"]}
    assert fields == {"name", "items[0]"}


@pytest.mark.urls(__name__)
def test_unauthenticated_is_a_problem(client):
    body = assert_problem(client.get("/api/v1/_private"), 403)
    assert body["type"].endswith("/not-authenticated")


@pytest.mark.urls(__name__)
def test_throttle_is_a_problem_with_retry_after(client):
    res = client.get("/api/v1/_throttled")
    assert_problem(res, 429)
    assert res["Retry-After"] == "30"


@pytest.mark.urls(__name__)
def test_unknown_url_is_a_json_problem(client):
    body = assert_problem(client.get("/api/v1/does-not-exist"), 404)
    assert body["type"].endswith("/not-found")


@pytest.mark.urls(__name__)
def test_server_error_hides_internals(client):
    client.raise_request_exception = False
    res = client.get("/api/v1/_boom")
    body = assert_problem(res, 500)
    assert "internal detail" not in res.content.decode()
    assert body["type"].endswith("/server-error")


@pytest.mark.django_db
def test_request_id_is_generated_and_echoed(client):
    generated = client.get("/api/v1/health")["X-Request-ID"]
    assert len(generated) == 32
    assert client.get("/api/v1/health", HTTP_X_REQUEST_ID="lb-abc12345")["X-Request-ID"] == (
        "lb-abc12345"
    )


@pytest.mark.django_db
def test_unsafe_request_id_is_replaced(client):
    rid = client.get("/api/v1/health", HTTP_X_REQUEST_ID="bad id\nInjected: 1")["X-Request-ID"]
    assert rid != "bad id\nInjected: 1" and len(rid) == 32


def test_json_log_line_carries_request_id():
    record = logging.LogRecord("pi360", logging.INFO, __file__, 1, "hello %s", ("x",), None)
    RequestIdFilter().filter(record)
    record.request_id = "abc12345"
    line = json.loads(JsonFormatter().format(record))
    assert line["message"] == "hello x"
    assert line["request_id"] == "abc12345"
    assert line["level"] == "INFO"


def test_throttles_and_cursor_pagination_are_defaults(settings):
    rf = settings.REST_FRAMEWORK
    assert rf["DEFAULT_PAGINATION_CLASS"].endswith("DefaultCursorPagination")
    assert {"anon", "user"} <= rf["DEFAULT_THROTTLE_RATES"].keys()


@pytest.mark.urls(__name__)
def test_django_request_log_carries_request_id(client, caplog):
    caplog.handler.addFilter(RequestIdFilter())
    res = client.post("/api/v1/_echo", {}, content_type="application/json")
    ids = {getattr(r, "request_id", None) for r in caplog.records if r.name == "django.request"}
    assert ids == {res["X-Request-ID"]}
