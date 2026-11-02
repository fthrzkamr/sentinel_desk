from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginView,
    LogoutView,
    MeView,
    TwoFactorDisableView,
    TwoFactorLoginView,
    TwoFactorSetupView,
    TwoFactorVerifyView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("login/2fa/", TwoFactorLoginView.as_view(), name="auth-login-2fa"),
    path("2fa/setup/", TwoFactorSetupView.as_view(), name="auth-2fa-setup"),
    path("2fa/verify/", TwoFactorVerifyView.as_view(), name="auth-2fa-verify"),
    path("2fa/disable/", TwoFactorDisableView.as_view(), name="auth-2fa-disable"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
]
