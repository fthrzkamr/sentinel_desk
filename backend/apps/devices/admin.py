from django.contrib import admin

from .models import AgentRelease, Branch, Company, Department, Device, DeviceCredential, Employee, EnrollmentToken


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "company")
    list_filter = ("company",)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "branch")
    list_filter = ("branch",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "department", "email")
    search_fields = ("full_name", "email")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("device_id", "hostname", "username", "status", "last_seen", "first_registered")
    list_filter = ("status", "company", "branch")
    search_fields = ("device_id", "hostname", "username", "serial_number")
    readonly_fields = ("device_id", "first_registered")


@admin.register(DeviceCredential)
class DeviceCredentialAdmin(admin.ModelAdmin):
    list_display = ("device", "created_at", "last_used_at")
    readonly_fields = ("token_hash",)


@admin.register(EnrollmentToken)
class EnrollmentTokenAdmin(admin.ModelAdmin):
    list_display = ("token_prefix", "label", "created_by", "created_at", "expires_at", "used_at", "revoked")
    list_filter = ("revoked",)
    readonly_fields = ("token_hash", "token_prefix")


@admin.register(AgentRelease)
class AgentReleaseAdmin(admin.ModelAdmin):
    list_display = ("version", "is_active", "file_size", "uploaded_by", "released_at")
    list_filter = ("is_active",)
    readonly_fields = ("sha256", "file_size", "released_at")
