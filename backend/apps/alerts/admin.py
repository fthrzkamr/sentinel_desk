from django.contrib import admin

from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("device", "category", "severity", "status", "triggered_at")
    list_filter = ("category", "severity", "status")
    search_fields = ("device__device_id", "message")
    date_hierarchy = "triggered_at"
