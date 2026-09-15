from django.urls import path

from .views import AgentSoftwareSyncView, SoftwareListView

urlpatterns = [
    path("agent/software/", AgentSoftwareSyncView.as_view(), name="agent-software-sync"),
    path("software/", SoftwareListView.as_view(), name="software-list"),
]
