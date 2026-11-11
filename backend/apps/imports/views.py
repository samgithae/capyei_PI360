"""Import API (T-040). Uploading and reading need imports.run; approving, committing and rolling
back need imports.commit."""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission

from . import services
from .models import ImportBatch, MappingTemplate, ReconciliationSignoff

RUN, COMMIT = "imports.run", "imports.commit"


def _run(fn, **kwargs):
    try:
        return fn(**kwargs)
    except services.ImportFailure as exc:
        raise serializers.ValidationError({exc.field: [exc.message]}) from exc


def _batch(pk) -> ImportBatch:
    try:
        return ImportBatch.objects.select_related("template").get(pk=pk)
    except ImportBatch.DoesNotExist:
        raise NotFound from None


def _template_out(t):
    return {
        "id": str(t.pk),
        "source": t.source,
        "version": t.version,
        "target": t.target,
        "columns": t.columns,
        "active": t.active,
    }


def _batch_out(b):
    return {
        "id": str(b.pk),
        "file_name": b.file_name,
        "status": b.status,
        "template": str(b.template),
        "target": b.template.target,
        "counts": b.counts,
        "defaults": b.defaults,
        "reference_plan": [{"kind": i["kind"], "label": i["label"]} for i in b.reference_plan],
        "duplicate_of": str(b.duplicate_of_id) if b.duplicate_of_id else None,
        "created_at": b.created_at.isoformat(),
        "committed_at": b.committed_at.isoformat() if b.committed_at else None,
    }


class TemplateInputSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=60)
    columns = serializers.DictField(child=serializers.CharField())
    target = serializers.CharField(default="participants")


class UploadSerializer(serializers.Serializer):
    template = serializers.UUIDField()
    file = serializers.FileField()
    defaults = serializers.JSONField(required=False, default=dict)


class InspectSerializer(serializers.Serializer):
    file = serializers.FileField()
    target = serializers.ChoiceField(choices=services.TARGETS, default="participants")


class ClusterDecisionSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=200)
    spellings = serializers.ListField(child=serializers.CharField(max_length=300), min_length=1)
    action = serializers.ChoiceField(choices=["link", "create", "apart"])
    employer_id = serializers.UUIDField(required=False, allow_null=True)


class StatusMapSerializer(serializers.Serializer):
    source_value = serializers.CharField(max_length=200)
    status = serializers.CharField(max_length=40, allow_blank=True)
    pathway = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    is_placement = serializers.BooleanField(required=False, default=True)


class PromoteSerializer(serializers.Serializer):
    programme_code = serializers.CharField(max_length=20)
    columns = serializers.DictField(child=serializers.CharField(allow_blank=True))


class RollbackSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class TemplateListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": RUN, "POST": RUN}

    @extend_schema(operation_id="imports_templates_list", responses={200: dict})
    def get(self, request):
        return Response(
            [_template_out(t) for t in MappingTemplate.objects.order_by("source", "-version")]
        )

    @extend_schema(request=TemplateInputSerializer, responses={201: dict})
    def post(self, request):
        s = TemplateInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        t = _run(services.create_template, actor=request.user, **s.validated_data)
        return Response(_template_out(t), status=status.HTTP_201_CREATED)


class InspectView(APIView):
    """Read-only look at a file's headers before any mapping exists. Stores nothing."""

    permission_classes = [HasPermission]
    required_permission = {"POST": RUN}
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request={"multipart/form-data": InspectSerializer}, responses={200: dict})
    def post(self, request):
        s = InspectSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        f = s.validated_data["file"]
        return Response(
            _run(
                services.inspect, file_name=f.name, data=f.read(), target=s.validated_data["target"]
            )
        )


class BatchListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": RUN, "POST": RUN}
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(operation_id="imports_batches_list", responses={200: dict})
    def get(self, request):
        qs = ImportBatch.objects.select_related("template")[:200]
        return Response([_batch_out(b) for b in qs])

    @extend_schema(request={"multipart/form-data": UploadSerializer}, responses={201: dict})
    def post(self, request):
        s = UploadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            template = MappingTemplate.objects.get(pk=s.validated_data["template"], active=True)
        except MappingTemplate.DoesNotExist:
            raise serializers.ValidationError({"template": ["Unknown template."]}) from None
        f = s.validated_data["file"]
        batch = _run(
            services.upload,
            actor=request.user,
            template=template,
            file_name=f.name,
            data=f.read(),
            defaults=s.validated_data.get("defaults"),
        )
        return Response(_batch_out(batch), status=status.HTTP_201_CREATED)


class BatchDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": RUN}

    @extend_schema(operation_id="imports_batch_detail", responses={200: dict})
    def get(self, request, pk):
        return Response(_batch_out(_batch(pk)))


class BatchRowsView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": RUN}

    @extend_schema(
        operation_id="imports_batch_rows",
        parameters=[
            OpenApiParameter("outcome", str),
            OpenApiParameter("offset", int),
        ],
        responses={200: dict},
    )
    def get(self, request, pk):
        rows = _batch(pk).rows.order_by("row_no")
        if outcome := request.query_params.get("outcome"):
            rows = rows.filter(outcome=outcome)
        try:
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except ValueError:
            offset = 0
        page = rows[offset : offset + 200]
        return Response(
            {
                "total": rows.count(),
                "rows": [
                    {
                        "row": r.row_no,
                        "outcome": r.outcome,
                        "match": r.match,
                        "source_key": r.source_key,
                        "errors": r.errors,
                        "warnings": r.warnings,
                        "diff": r.diff,
                        "committed": r.committed,
                    }
                    for r in page
                ],
            }
        )


class BatchErrorsView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": RUN}

    @extend_schema(operation_id="imports_batch_errors", responses={200: bytes})
    def get(self, request, pk):
        resp = HttpResponse(services.error_report(_batch(pk)), content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="import-{pk}-errors.csv"'
        return resp


class ApproveSerializer(serializers.Serializer):
    create_reference = serializers.BooleanField(required=False, default=False)


def _action(name, perm, fn_name, with_reason=False):
    class View(APIView):
        permission_classes = [HasPermission]
        required_permission = {"POST": perm}

        @extend_schema(
            operation_id=f"imports_batch_{name}",
            request=(
                RollbackSerializer
                if with_reason
                else ApproveSerializer
                if name == "approve"
                else None
            ),
            responses={200: dict},
        )
        def post(self, request, pk):
            batch = _batch(pk)
            kwargs = {}
            if with_reason:
                s = RollbackSerializer(data=request.data)
                s.is_valid(raise_exception=True)
                kwargs["reason"] = s.validated_data["reason"]
            if name == "approve":
                s = ApproveSerializer(data=request.data)
                s.is_valid(raise_exception=True)
                kwargs["create_reference"] = s.validated_data["create_reference"]
            _run(getattr(services, fn_name), actor=request.user, batch=batch, **kwargs)
            batch.refresh_from_db()
            return Response(_batch_out(batch))

    View.__name__ = f"Batch{name.capitalize()}View"
    return View


BatchApproveView = _action("approve", COMMIT, "approve")
BatchCommitView = _action("commit", COMMIT, "commit")
BatchRollbackView = _action("rollback", COMMIT, "rollback", with_reason=True)
BatchCancelView = _action("cancel", RUN, "cancel")


class BatchReconciliationView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": RUN}

    @extend_schema(
        operation_id="imports_batch_reconciliation",
        parameters=[OpenApiParameter("download", str)],
        responses={200: dict},
    )
    def get(self, request, pk):
        batch = _batch(pk)
        if request.query_params.get("download") == "csv":
            resp = HttpResponse(services.reconciliation_csv(batch), content_type="text/csv")
            resp["Content-Disposition"] = f'attachment; filename="import-{pk}-reconciliation.csv"'
            return resp
        return Response(services.reconciliation(batch))


def _signoff_out(s):
    return {
        "signer_name": s.signer_name,
        "signer_role": s.signer_role,
        "signed_on": s.signed_on.isoformat(),
        "note": s.note,
        "recorded_at": s.created_at.isoformat(),
    }


class SignoffInputSerializer(serializers.Serializer):
    signer_name = serializers.CharField(max_length=120)
    signer_role = serializers.CharField(max_length=120)
    signed_on = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class BatchSignoffView(APIView):
    """GET reads the sign-off ({signed: false} until signed); POST records it (imports.commit)."""

    permission_classes = [HasPermission]
    required_permission = {"GET": RUN, "POST": COMMIT}

    @extend_schema(operation_id="imports_batch_signoff_read", responses={200: dict})
    def get(self, request, pk):
        batch = _batch(pk)
        s = ReconciliationSignoff.objects.filter(batch=batch).first()
        return Response({"signed": True, **_signoff_out(s)} if s else {"signed": False})

    @extend_schema(
        operation_id="imports_batch_signoff",
        request=SignoffInputSerializer,
        responses={201: dict},
    )
    def post(self, request, pk):
        batch = _batch(pk)
        s = SignoffInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        signed = _run(services.sign_off, actor=request.user, batch=batch, **s.validated_data)
        return Response(_signoff_out(signed), status=status.HTTP_201_CREATED)


class TemplateContractView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": RUN}

    @extend_schema(operation_id="imports_template_contract", responses={200: dict})
    def get(self, request, pk):
        template = get_object_or_404(MappingTemplate, pk=pk)
        return Response(services.contract(template))


class PlacementReviewView(APIView):
    """Name groups and unmapped statuses for a placement batch; stewards settle them here."""

    permission_classes = [HasPermission]
    required_permission = {"GET": RUN}

    @extend_schema(operation_id="imports_batch_review", responses={200: dict})
    def get(self, request, pk):
        return Response(_run(services.placement_review, batch=_batch(pk)))


class PlacementEmployerDecisionView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": COMMIT}

    @extend_schema(request=ClusterDecisionSerializer, responses={200: dict})
    def post(self, request, pk):
        s = ClusterDecisionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        employer_id = str(d["employer_id"]) if d.get("employer_id") else None
        return Response(
            _run(
                services.decide_employer_group,
                actor=request.user,
                batch=_batch(pk),
                key=d["key"],
                spellings=d["spellings"],
                action=d["action"],
                employer_id=employer_id,
            )  # fmt: skip
        )


class PlacementStatusMapView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": COMMIT}

    @extend_schema(request=StatusMapSerializer, responses={200: dict})
    def post(self, request, pk):
        s = StatusMapSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(
            _run(
                services.map_placement_status,
                actor=request.user,
                batch=_batch(pk),
                **s.validated_data,
            )  # fmt: skip
        )


class PlacementProposedStatusesView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"POST": COMMIT}

    @extend_schema(request=None, responses={200: dict})
    def post(self, request, pk):
        return Response(_run(services.load_proposed_statuses, actor=request.user, batch=_batch(pk)))


BatchRecheckView = _action("recheck", COMMIT, "recheck")


class ExtraSummaryView(APIView):
    """Which extra labels the people of one programme carry (stage E: promote extras)."""

    permission_classes = [HasPermission]
    required_permission = {"GET": RUN}

    @extend_schema(
        operation_id="imports_extra_summary",
        parameters=[OpenApiParameter("programme", str, required=True)],
        responses={200: dict},
    )
    def get(self, request):
        return Response(services.extra_summary(request.query_params.get("programme", "")))


class ExtraPromoteView(APIView):
    """Turn extra data into a placement import batch, to be reviewed and loaded like any other."""

    permission_classes = [HasPermission]
    required_permission = {"POST": COMMIT}

    @extend_schema(request=PromoteSerializer, responses={201: dict})
    def post(self, request):
        s = PromoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        batch = _run(
            services.promote_extra,
            actor=request.user,
            programme_code=s.validated_data["programme_code"],
            columns=s.validated_data["columns"],
        )
        return Response(_batch_out(batch), status=status.HTTP_201_CREATED)
