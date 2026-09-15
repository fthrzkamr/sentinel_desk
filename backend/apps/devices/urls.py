from django.urls import path

from .views import (
    AgentEnrollView,
    AgentHeartbeatView,
    DeviceDetailView,
    DeviceDisableView,
    DeviceEnableView,
    DeviceListView,
    EnrollmentTokenListCreateView,
    EnrollmentTokenRevokeView,
)

urlpatterns = [
    # Admin-facing
    path("devices/", DeviceListView.as_view(), name="device-list"),
    path("devices/<str:device_id>/", DeviceDetailView.as_view(), name="device-detail"),
    path("devices/<str:device_id>/disable/", DeviceDisableView.as_view(), name="device-disable"),
    path("devices/<str:device_id>/enable/", DeviceEnableView.as_view(), name="device-enable"),
    path(
        "agent/enrollment-tokens/",
        EnrollmentTokenListCreateView.as_view(),
        name="enrollment-token-list-create",
    ),
    path(
        "agent/enrollment-tokens/<int:pk>/revoke/",
        EnrollmentTokenRevokeView.as_view(),
        name="enrollment-token-revoke",
    ),
    # Agent-facing
    path("agent/enroll/", AgentEnrollView.as_view(), name="agent-enroll"),
    path("agent/heartbeat/", AgentHeartbeatView.as_view(), name="agent-heartbeat"),
]
