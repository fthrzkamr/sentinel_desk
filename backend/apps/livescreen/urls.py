from django.urls import path

from .views import LiveScreenStatusView

urlpatterns = [
    path("devices/<str:device_id>/live-screen-status/", LiveScreenStatusView.as_view(), name="live-screen-status"),
]
