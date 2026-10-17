from django.contrib import admin

from .models import AppUsage, BrowsingHistoryEntry, FileActivityEvent


@admin.register(AppUsage)
class AppUsageAdmin(admin.ModelAdmin):
    list_display = ("device", "app_name", "date", "duration_seconds")
    list_filter = ("date",)
    search_fields = ("app_name", "device__device_id", "device__hostname")


@admin.register(BrowsingHistoryEntry)
class BrowsingHistoryEntryAdmin(admin.ModelAdmin):
    list_display = ("device", "browser", "url", "visited_at")
    list_filter = ("browser",)
    search_fields = ("url", "title", "device__device_id")


@admin.register(FileActivityEvent)
class FileActivityEventAdmin(admin.ModelAdmin):
    list_display = ("device", "event_type", "path", "occurred_at")
    list_filter = ("event_type",)
    search_fields = ("path", "device__device_id")
