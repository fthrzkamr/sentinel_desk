from django.contrib.auth.models import AbstractUser
from django.db import models


class Permission(models.Model):
    """Granular permission code, e.g. 'device.view'. Checked in DRF permission
    classes, never only hidden in the frontend."""

    code = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=255, blank=True)
    permissions = models.ManyToManyField(Permission, related_name="roles", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    email = models.EmailField(unique=True)
    role = models.ForeignKey(
        Role, null=True, blank=True, on_delete=models.SET_NULL, related_name="users"
    )

    def has_permission_code(self, code: str) -> bool:
        if self.is_superuser:
            return True
        if not self.role_id:
            return False
        return self.role.permissions.filter(code=code).exists()

    def permission_codes(self) -> list[str]:
        if self.is_superuser:
            return list(Permission.objects.values_list("code", flat=True))
        if not self.role_id:
            return []
        return list(self.role.permissions.values_list("code", flat=True))

    def __str__(self):
        return self.username
