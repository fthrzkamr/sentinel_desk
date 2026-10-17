from django.urls import path

from .views import (
    AgentSoftwareSyncView,
    SoftwareListView,
    SoftwareWhitelistDeleteView,
    SoftwareWhitelistListCreateView,
)

urlpatterns = [
    path("agent/software/", AgentSoftwareSyncView.as_view(), name="agent-software-sync"),
    path("software/", SoftwareListView.as_view(), name="software-list"),
    path("software-whitelist/", SoftwareWhitelistListCreateView.as_view(), name="software-whitelist-list"),
    path("software-whitelist/<int:pk>/", SoftwareWhitelistDeleteView.as_view(), name="software-whitelist-delete"),
]
