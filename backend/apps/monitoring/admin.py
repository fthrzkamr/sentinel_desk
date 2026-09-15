from django.contrib import admin

from .models import DeviceMetric


@admin.register(DeviceMetric)
class DeviceMetricAdmin(admin.ModelAdmin):
    list_display = ("device", "recorded_at", "cpu_percent", "ram_percent", "disk_percent", "battery_percent")
    list_filter = ("device",)
    date_hierarchy = "recorded_at"
