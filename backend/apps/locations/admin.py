from django.contrib import admin

from .models import Location


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("device", "source", "latitude", "longitude", "accuracy_meters", "recorded_at")
    list_filter = ("source", "device")
    date_hierarchy = "recorded_at"
