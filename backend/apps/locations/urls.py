from django.urls import path

from .views import AgentLocationView, DeviceLocationHistoryView, LocationLatestListView

urlpatterns = [
    path("agent/location/", AgentLocationView.as_view(), name="agent-location"),
    path("locations/", LocationLatestListView.as_view(), name="location-latest-list"),
    path("devices/<str:device_id>/locations/", DeviceLocationHistoryView.as_view(), name="device-location-history"),
]
