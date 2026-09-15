from django.urls import path

from .views import AlertAcknowledgeView, AlertListView, AlertResolveView, AlertSummaryView

urlpatterns = [
    path("alerts/", AlertListView.as_view(), name="alert-list"),
    path("alerts/summary/", AlertSummaryView.as_view(), name="alert-summary"),
    path("alerts/<int:pk>/acknowledge/", AlertAcknowledgeView.as_view(), name="alert-acknowledge"),
    path("alerts/<int:pk>/resolve/", AlertResolveView.as_view(), name="alert-resolve"),
]
