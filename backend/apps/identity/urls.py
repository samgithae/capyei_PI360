from django.urls import path

from . import auth_views as a
from . import role_views as r
from .views import MeView

urlpatterns = [
    path("me", MeView.as_view(), name="me"),
    path("identity/permissions", r.PermissionCatalogueView.as_view(), name="identity-permissions"),
    path("identity/roles", r.RoleListView.as_view(), name="identity-roles"),
    path("identity/roles/<int:pk>", r.RoleDetailView.as_view(), name="identity-role"),
    path("auth/login", a.LoginView.as_view(), name="auth-login"),
    path("auth/logout", a.LogoutView.as_view(), name="auth-logout"),
    path("auth/mfa/setup", a.MfaSetupView.as_view(), name="auth-mfa-setup"),
    path("auth/mfa/confirm", a.MfaConfirmView.as_view(), name="auth-mfa-confirm"),
    path("auth/mfa/verify", a.MfaVerifyView.as_view(), name="auth-mfa-verify"),
    path("auth/password/change", a.PasswordChangeView.as_view(), name="auth-password-change"),
    path("auth/password/reset", a.PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path(
        "auth/password/reset/confirm",
        a.PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
]
