from django.urls import path

from .views import AgentBinaryUploadView, SystemSettingsView, TestNotificationView

urlpatterns = [
    path("settings/", SystemSettingsView.as_view(), name="system-settings"),
    path("settings/test-notification/", TestNotificationView.as_view(), name="system-settings-test-notification"),
    path("settings/agent-binary/", AgentBinaryUploadView.as_view(), name="system-settings-agent-binary"),
]
