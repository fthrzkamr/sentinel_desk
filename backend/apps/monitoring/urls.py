from django.urls import path

from .views import AgentMetricsView, DeviceMetricHistoryView, DeviceMetricLatestView

urlpatterns = [
    path("agent/metrics/", AgentMetricsView.as_view(), name="agent-metrics"),
    path("devices/<str:device_id>/metrics/", DeviceMetricLatestView.as_view(), name="device-metrics-latest"),
    path("devices/<str:device_id>/history/", DeviceMetricHistoryView.as_view(), name="device-metrics-history"),
]
