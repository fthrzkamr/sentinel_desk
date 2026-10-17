from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.accounts.management_urls")),
    path("api/", include("apps.devices.urls")),
    path("api/", include("apps.monitoring.urls")),
    path("api/", include("apps.software.urls")),
    path("api/", include("apps.locations.urls")),
    path("api/", include("apps.livescreen.urls")),
    path("api/", include("apps.alerts.urls")),
    path("api/", include("apps.audit.urls")),
    path("api/", include("apps.system_settings.urls")),
    path("api/", include("apps.device_activity.urls")),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
