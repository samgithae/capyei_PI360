"""Rules API (T-047). intelligence.view reads; intelligence.manage_rules drafts (create, edit,
copy, send for review, discard); intelligence.approve_rules decides (return, approve, activate,
deactivate). Keeping the two apart lets a deployment require a second person to approve."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

import pi360_rules
from apps.api.access import HasPermission, has_permission
from apps.audit import services as audit

from . import services
from .models import RuleSet, RuleVersion

VIEW, MANAGE, APPROVE = (
    "intelligence.view", "intelligence.manage_rules", "intelligence.approve_rules"
)  # fmt: skip
MODULE_NAMES = dict(RuleSet.MODULES)
STATUS_NAMES = dict(RuleVersion.STATUSES)
# action -> (permission, statuses it is offered in)
ACTIONS = {
    "edit": (MANAGE, {RuleVersion.DRAFT}),
    "submit": (MANAGE, {RuleVersion.DRAFT}),
    "discard": (MANAGE, {RuleVersion.DRAFT}),
    "clone": (MANAGE, set(STATUS_NAMES)),
    "return": (APPROVE, {RuleVersion.IN_REVIEW, RuleVersion.APPROVED}),
    "approve": (APPROVE, {RuleVersion.IN_REVIEW}),
    "activate": (APPROVE, {RuleVersion.APPROVED}),
    "deactivate": (APPROVE, {RuleVersion.ACTIVE}),
}


def _violation(exc):
    return Response(
        {"errors": [{"field": exc.field, "message": exc.message, "code": exc.code}]},
        status=status.HTTP_409_CONFLICT,
    )


def _user_name(u):
    return (u.get_full_name() or u.get_username()) if u else ""


def _iso(dt):
    return dt.isoformat() if dt else None


def _version(v):
    d = v.definition if isinstance(v.definition, dict) else {}
    return {
        "id": str(v.pk),
        "number": v.number,
        "status": v.status,
        "status_label": STATUS_NAMES[v.status],
        "change_notes": v.change_notes,
        "factors": len(d.get("factors") or []),
        "waiting": len(services.unapproved(v)),
        "created_by": _user_name(v.created_by),
        "created_at": _iso(v.created_at),
        "approved_by": _user_name(v.approved_by),
        "approved_at": _iso(v.approved_at),
        "effective_from": _iso(v.effective_from),
        "retired_at": _iso(v.retired_at),
        "used": v.used_at is not None,
    }


def _rule_set(rs, versions):
    active = next((v for v in versions if v.status == RuleVersion.ACTIVE), None)
    return {
        "id": str(rs.pk),
        "module": rs.module,
        "module_label": MODULE_NAMES[rs.module],
        "code": rs.code,
        "name": rs.name,
        "purpose": rs.purpose,
        "active": _version(active) if active else None,
        "latest": _version(versions[0]) if versions else None,
        "version_count": len(versions),
    }


def _versions(rs):
    return list(rs.versions.select_related("created_by", "approved_by").order_by("-number"))


def _detail(v, user):
    return {
        **_version(v),
        "rule_set": {
            "id": str(v.rule_set_id),
            "code": v.rule_set.code,
            "name": v.rule_set.name,
            "module": v.rule_set.module,
            "module_label": MODULE_NAMES[v.rule_set.module],
        },
        "definition": v.definition,
        "definition_hash": services.definition_hash(v.definition),
        "problems": services.problems(v),
        "unapproved": services.unapproved(v),
        "submitted_by": _user_name(v.submitted_by),
        "submitted_at": _iso(v.submitted_at),
        "activated_by": _user_name(v.activated_by),
        "cloned_from": v.cloned_from.number if v.cloned_from_id else None,
        "actions": [
            name
            for name, (permission, statuses) in ACTIONS.items()
            if v.status in statuses and has_permission(user, permission)
        ],
    }


def _get(pk):
    try:
        return RuleVersion.objects.select_related(
            "rule_set", "created_by", "submitted_by", "approved_by", "activated_by", "cloned_from"
        ).get(pk=pk)
    except RuleVersion.DoesNotExist:
        raise NotFound from None


class RuleSetCreateSerializer(serializers.Serializer):
    module = serializers.ChoiceField(choices=list(pi360_rules.MODULES))
    code = serializers.SlugField(max_length=60)
    name = serializers.CharField(max_length=120)
    purpose = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class VersionEditSerializer(serializers.Serializer):
    definition = serializers.JSONField(required=False)
    change_notes = serializers.CharField(required=False, allow_blank=True, max_length=4000)


class NoteSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class RuleSetListView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "POST": MANAGE}

    @extend_schema(operation_id="rules_list", responses={200: dict(type="array", items={})})
    def get(self, request):
        sets = RuleSet.objects.prefetch_related("versions__created_by", "versions__approved_by")
        return Response(
            [_rule_set(rs, sorted(rs.versions.all(), key=lambda v: -v.number)) for rs in sets]
        )

    @extend_schema(request=RuleSetCreateSerializer, responses={201: dict, 409: dict})
    def post(self, request):
        s = RuleSetCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            rs = services.create_rule_set(actor=request.user, **s.validated_data)
        except services.RuleViolation as exc:
            return _violation(exc)
        versions = _versions(rs)
        return Response(
            {**_rule_set(rs, versions), "versions": [_version(v) for v in versions]},
            status=status.HTTP_201_CREATED,
        )


def _settings_payload():
    from .settings_registry import REGISTRY

    values = services.setting_values()
    return [
        {
            "key": m.key,
            "group": m.group,
            "label": m.label,
            "unit": m.unit,
            "help": m.help,
            "default": m.default,
            "minimum": m.minimum,
            "value": values[m.key],
        }
        for m in REGISTRY
    ]


class RuleSettingsView(APIView):
    """The numbers behind support flags and employer evidence. Anyone who can see rules reads
    them; changing them needs intelligence.manage_rules. Every change is audited."""

    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "PUT": MANAGE}

    @extend_schema(operation_id="rule_settings_get", responses={200: dict(type="array", items={})})
    def get(self, request):
        return Response(_settings_payload())

    @extend_schema(
        operation_id="rule_settings_put",
        request=dict,
        responses={200: dict(type="array", items={})},
    )
    def put(self, request):
        values = request.data.get("values") if isinstance(request.data, dict) else None
        if not isinstance(values, dict) or not values:
            raise serializers.ValidationError({"values": ["Send the numbers to change."]})
        try:
            services.update_settings(actor=request.user, values=values)
        except services.RuleViolation as exc:
            raise serializers.ValidationError({exc.field: [exc.message]}) from exc
        return Response(_settings_payload())


class EmployerEvidenceView(APIView):
    """Module C evidence for one employer: counts, period and source for each indicator."""

    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="employer_evidence", responses={200: dict})
    def get(self, request, pk):
        from datetime import date

        from apps.employers import services as employers

        if not employers.exists(pk):
            raise NotFound()
        return Response(services.employer_evidence(pk, date.today()))


class SupportQueueView(APIView):
    """Module A review queue: youth who may need extra support, with the reason for each flag.
    Scope limits whose flags are shown."""

    permission_classes = [HasPermission]
    required_permission = {"GET": "participants.view_profile"}

    @extend_schema(operation_id="support_queue", responses={200: dict})
    def get(self, request):
        from datetime import date

        from apps.participants import services as participants

        return Response(
            services.support_queue(
                participants.visible_ids(request.user).values_list("pk", flat=True), date.today()
            )
        )


class SupportReviewView(APIView):
    """An officer records that they looked at a flagged youth (pauses the flag for a while)."""

    permission_classes = [HasPermission]
    required_permission = {"POST": "referrals.edit"}

    @extend_schema(operation_id="support_review", request=dict, responses={204: None})
    def post(self, request, pk):
        from apps.participants import services as participants

        p = participants.find_active(pk) if participants.is_visible(request.user, pk) else None
        if p is None:
            raise NotFound()
        data = request.data if isinstance(request.data, dict) else {}
        flags = data.get("flags") if isinstance(data.get("flags"), list) else []
        try:
            services.review_support(
                actor=request.user,
                participant=p,
                outcome=str(data.get("outcome", "")),
                note=str(data.get("note", "")),
                flags=[str(f) for f in flags],
            )
        except services.RuleViolation as exc:
            raise serializers.ValidationError({exc.field: [exc.message]}) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class OperatorListView(APIView):
    """The fixed operators a factor may use, for the rules screen."""

    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="rules_operators", responses={200: dict(type="array", items={})})
    def get(self, request):
        return Response(
            [
                {"code": op.code, "label": op.label, "expects": op.expects}
                for op in pi360_rules.OPERATORS.values()
            ]
        )


class RuleSetDetailView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(operation_id="rules_detail", responses={200: dict})
    def get(self, request, pk):
        try:
            rs = RuleSet.objects.get(pk=pk)
        except RuleSet.DoesNotExist:
            raise NotFound from None
        versions = _versions(rs)
        return Response({**_rule_set(rs, versions), "versions": [_version(v) for v in versions]})


class RuleVersionView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW, "PATCH": MANAGE, "DELETE": MANAGE}

    @extend_schema(operation_id="rules_version", responses={200: dict})
    def get(self, request, pk):
        return Response(_detail(_get(pk), request.user))

    @extend_schema(request=VersionEditSerializer, responses={200: dict, 409: dict})
    def patch(self, request, pk):
        v = _get(pk)
        s = VersionEditSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.update_draft(
                actor=request.user,
                version=v,
                definition=s.validated_data.get("definition"),
                change_notes=s.validated_data.get("change_notes"),
            )
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_detail(_get(pk), request.user))

    @extend_schema(operation_id="rules_version_discard", responses={204: None, 409: dict})
    def delete(self, request, pk):
        try:
            services.discard(actor=request.user, version=_get(pk))
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class _StepView(APIView):
    """One lifecycle step. Subclasses name the permission and the service call."""

    permission_classes = [HasPermission]
    step = None

    def run(self, request, version, note):
        raise NotImplementedError

    @extend_schema(request=NoteSerializer, responses={200: dict, 409: dict})
    def post(self, request, pk):
        v = _get(pk)
        s = NoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            result = self.run(request, v, s.validated_data["note"])
        except services.RuleViolation as exc:
            return _violation(exc)
        return Response(_detail(_get(result.pk if result is not None else pk), request.user))


class RuleVersionCloneView(_StepView):
    required_permission = {"POST": MANAGE}

    def run(self, request, version, note):
        return services.clone(actor=request.user, version=version, change_notes=note)


class RuleVersionSubmitView(_StepView):
    required_permission = {"POST": MANAGE}

    def run(self, request, version, note):
        return services.submit(actor=request.user, version=version)


class RuleVersionReturnView(_StepView):
    required_permission = {"POST": APPROVE}

    def run(self, request, version, note):
        return services.send_back(actor=request.user, version=version, note=note)


class RuleVersionApproveView(_StepView):
    required_permission = {"POST": APPROVE}

    def run(self, request, version, note):
        return services.approve(actor=request.user, version=version, note=note)


class RuleVersionActivateView(_StepView):
    required_permission = {"POST": APPROVE}

    def run(self, request, version, note):
        return services.activate(actor=request.user, version=version, note=note)


class RuleVersionDeactivateView(_StepView):
    """Answers with the deactivated version; its rule set page shows what is now in force."""

    required_permission = {"POST": APPROVE}

    def run(self, request, version, note):
        services.deactivate(actor=request.user, version=version, reason=note)
        return version


class RuleVersionHistoryView(APIView):
    permission_classes = [HasPermission]
    required_permission = {"GET": VIEW}

    @extend_schema(
        operation_id="rules_version_history", responses={200: dict(type="array", items={})}
    )
    def get(self, request, pk):
        return Response(audit.history("rule_version", _get(pk).pk))


class OpportunitySuggestionsView(APIView):
    """Suggested youth for an opportunity, from the active Compatibility rule. Gated on
    permission to see youth profiles; scope limits which youth are ranked."""

    permission_classes = [HasPermission]
    required_permission = {"GET": "participants.view_profile"}

    @extend_schema(operation_id="opportunity_suggestions", responses={200: dict(type="object")})
    def get(self, request, pk):
        from datetime import date

        from apps.participants import services as participants

        try:
            limit = max(1, min(int(request.query_params.get("limit", 50)), 200))
        except ValueError:
            limit = 50
        out = services.suggest_youth(
            pk,
            participants.visible_ids(request.user).values_list("pk", flat=True),
            date.today(),
            limit,
        )
        if out is None:
            raise NotFound()
        return Response(out)
