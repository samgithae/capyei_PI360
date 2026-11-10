from rest_framework import serializers


class MeSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    username = serializers.CharField(required=False)
    roles = serializers.ListField(child=serializers.CharField(), required=False)
    permissions = serializers.ListField(child=serializers.CharField(), required=False)
    scope = serializers.DictField(required=False)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


class LoginResultSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "mfa_required"])
    mfa_enrolled = serializers.BooleanField(required=False)


class MfaCodeSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^\d{6}$", error_messages={"invalid": "Enter the 6-digit code."})


class MfaSetupSerializer(serializers.Serializer):
    config_url = serializers.CharField()


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=256, trim_whitespace=False)
    new_password = serializers.CharField(max_length=256, trim_whitespace=False)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(max_length=256, trim_whitespace=False)


class PermissionSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    group = serializers.CharField()
    grant_only = serializers.BooleanField()


class RoleSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=80)
    description = serializers.CharField(max_length=300, allow_blank=True, required=False)
    permissions = serializers.ListField(child=serializers.CharField(), required=False)
    scope_mode = serializers.ChoiceField(choices=["all", "assigned"], required=False)
    active = serializers.BooleanField(required=False)
    is_system = serializers.BooleanField(read_only=True)
    user_count = serializers.IntegerField(read_only=True)
