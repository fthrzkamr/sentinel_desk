from django.urls import path

from .views import (
    AgentAppUsageSyncView,
    AgentBrowsingHistorySyncView,
    AgentFileActivitySyncView,
    AgentIdleActivitySyncView,
    AgentSystemErrorSyncView,
    AgentUsbEventView,
    AppUsageListView,
    BrowsingHistoryListView,
    FileActivityListView,
    IdleActivityListView,
    SystemErrorListView,
)

urlpatterns = [
    path("agent/app-usage/", AgentAppUsageSyncView.as_view(), name="agent-app-usage-sync"),
    path("agent/browsing-history/", AgentBrowsingHistorySyncView.as_view(), name="agent-browsing-history-sync"),
    path("agent/file-activity/", AgentFileActivitySyncView.as_view(), name="agent-file-activity-sync"),
    path("agent/idle-activity/", AgentIdleActivitySyncView.as_view(), name="agent-idle-activity-sync"),
    path("agent/system-errors/", AgentSystemErrorSyncView.as_view(), name="agent-system-error-sync"),
    path("agent/usb-event/", AgentUsbEventView.as_view(), name="agent-usb-event"),
    path("app-usage/", AppUsageListView.as_view(), name="app-usage-list"),
    path("browsing-history/", BrowsingHistoryListView.as_view(), name="browsing-history-list"),
    path("file-activity/", FileActivityListView.as_view(), name="file-activity-list"),
    path("idle-activity/", IdleActivityListView.as_view(), name="idle-activity-list"),
    path("system-errors/", SystemErrorListView.as_view(), name="system-error-list"),
]
