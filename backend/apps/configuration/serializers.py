from rest_framework import serializers


class ReferenceInputSerializer(serializers.Serializer):
    """Open shape: the writable fields depend on the reference kind (see reference.KINDS)."""

    def to_internal_value(self, data):
        return dict(data)


class ReferenceReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class AliasSerializer(serializers.Serializer):
    alias = serializers.CharField()
    source = serializers.CharField(required=False, allow_blank=True, default="")
    scope = serializers.CharField(required=False, allow_blank=True, default="")


class FlagSerializer(serializers.Serializer):
    key = serializers.CharField(read_only=True)
    description = serializers.CharField(required=False, allow_blank=True)
    enabled = serializers.BooleanField(required=False)
    environments = serializers.ListField(child=serializers.CharField(), required=False)
    roles = serializers.ListField(child=serializers.CharField(), required=False)
    reason = serializers.CharField(required=False, allow_blank=True, write_only=True)


class SettingChangeSerializer(serializers.Serializer):
    key = serializers.CharField()
    value = serializers.IntegerField()
    reason = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    code = serializers.CharField(required=False, allow_blank=True, default="", write_only=True)


class SettingSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.IntegerField()
    default = serializers.IntegerField()
    min = serializers.IntegerField()
    max = serializers.IntegerField()
