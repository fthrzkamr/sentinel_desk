from django.urls import path

from .views import (
    AgentDownloadView,
    AgentEnrollView,
    AgentHeartbeatView,
    AgentReleaseDetailView,
    AgentReleaseListCreateView,
    AgentVersionView,
    BranchDetailView,
    BranchListCreateView,
    CompanyDetailView,
    CompanyListCreateView,
    DepartmentDetailView,
    DepartmentListCreateView,
    DeviceDetailView,
    DeviceDisableView,
    DeviceEnableView,
    DeviceListView,
    EmployeeDetailView,
    EmployeeListCreateView,
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
    # Org structure
    path("companies/", CompanyListCreateView.as_view(), name="company-list-create"),
    path("companies/<int:pk>/", CompanyDetailView.as_view(), name="company-detail"),
    path("branches/", BranchListCreateView.as_view(), name="branch-list-create"),
    path("branches/<int:pk>/", BranchDetailView.as_view(), name="branch-detail"),
    path("departments/", DepartmentListCreateView.as_view(), name="department-list-create"),
    path("departments/<int:pk>/", DepartmentDetailView.as_view(), name="department-detail"),
    path("employees/", EmployeeListCreateView.as_view(), name="employee-list-create"),
    path("employees/<int:pk>/", EmployeeDetailView.as_view(), name="employee-detail"),
    # Agent-facing
    path("agent/enroll/", AgentEnrollView.as_view(), name="agent-enroll"),
    path("agent/heartbeat/", AgentHeartbeatView.as_view(), name="agent-heartbeat"),
    path("agent/version/", AgentVersionView.as_view(), name="agent-version"),
    path("agent/download/", AgentDownloadView.as_view(), name="agent-download"),
    # Agent release management (admin)
    path("agent-releases/", AgentReleaseListCreateView.as_view(), name="agent-release-list-create"),
    path("agent-releases/<int:pk>/", AgentReleaseDetailView.as_view(), name="agent-release-detail"),
]
