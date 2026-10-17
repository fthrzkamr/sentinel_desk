from django.urls import path

from .views import (
    AlertAcknowledgeView,
    AlertListView,
    AlertResolveView,
    AlertSummaryView,
    DeviceRiskScoreView,
)

urlpatterns = [
    path("alerts/", AlertListView.as_view(), name="alert-list"),
    path("alerts/summary/", AlertSummaryView.as_view(), name="alert-summary"),
    path("alerts/<int:pk>/acknowledge/", AlertAcknowledgeView.as_view(), name="alert-acknowledge"),
    path("alerts/<int:pk>/resolve/", AlertResolveView.as_view(), name="alert-resolve"),
    path("devices/<str:device_id>/risk-score/", DeviceRiskScoreView.as_view(), name="device-risk-score"),
]
