from django.contrib import admin

from .models import Software


@admin.register(Software)
class SoftwareAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "publisher", "device", "install_date", "collected_at")
    list_filter = ("device",)
    search_fields = ("name", "publisher", "device__device_id", "device__hostname")
