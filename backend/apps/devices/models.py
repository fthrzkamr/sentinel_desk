import hashlib
import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone


class Company(models.Model):
    name = models.CharField(max_length=150, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "companies"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Branch(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=150)

    class Meta:
        unique_together = ("company", "name")
        ordering = ["company__name", "name"]

    def __str__(self):
        return f"{self.company.name} / {self.name}"


class Department(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="departments")
    name = models.CharField(max_length=150)

    class Meta:
        unique_together = ("branch", "name")
        ordering = ["branch__name", "name"]

    def __str__(self):
        return f"{self.branch} / {self.name}"


class Employee(models.Model):
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees"
    )
    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    position = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Device(models.Model):
    class Status(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        OFFLINE = "OFFLINE", "Offline"
        WARNING = "WARNING", "Warning"
        CRITICAL = "CRITICAL", "Critical"
        DISABLED = "DISABLED", "Disabled"

    device_id = models.CharField(max_length=20, unique=True, editable=False)

    hostname = models.CharField(max_length=150)
    computer_name = models.CharField(max_length=150, blank=True)
    username = models.CharField(max_length=150, blank=True)

    os_name = models.CharField(max_length=100, blank=True)
    os_version = models.CharField(max_length=100, blank=True)
    architecture = models.CharField(max_length=20, blank=True)

    cpu = models.CharField(max_length=200, blank=True)
    ram = models.CharField(max_length=100, blank=True)
    disk = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=150, blank=True)
    manufacturer = models.CharField(max_length=150, blank=True)
    model = models.CharField(max_length=150, blank=True)

    mac_address = models.CharField(max_length=17, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    agent_version = models.CharField(max_length=30, blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OFFLINE)
    last_seen = models.DateTimeField(null=True, blank=True)
    first_registered = models.DateTimeField(auto_now_add=True)

    company = models.ForeignKey(
        Company, on_delete=models.SET_NULL, null=True, blank=True, related_name="devices"
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="devices"
    )
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="devices"
    )
    assigned_employee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="devices"
    )

    class Meta:
        ordering = ["-first_registered"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["last_seen"]),
        ]

    def __str__(self):
        return f"{self.device_id} ({self.hostname})"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and not self.device_id:
            self.device_id = f"SD-LPT-{self.pk:06d}"
            super().save(update_fields=["device_id"])

    def mark_seen(self):
        self.last_seen = timezone.now()
        if self.status != Device.Status.DISABLED:
            self.status = Device.Status.ONLINE
        self.save(update_fields=["last_seen", "status"])


class DeviceCredential(models.Model):
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name="credential")
    token_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(48)

    @classmethod
    def create_for_device(cls, device: Device):
        raw_token = cls.generate_token()
        credential = cls.objects.create(device=device, token_hash=make_password(raw_token))
        return credential, raw_token

    def check_token(self, raw_token: str) -> bool:
        return check_password(raw_token, self.token_hash)

    def touch(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])


class EnrollmentToken(models.Model):
    token_hash = models.CharField(max_length=255)
    token_prefix = models.CharField(max_length=8, editable=False)
    label = models.CharField(max_length=150, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="enrollment_tokens"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    used_by_device = models.ForeignKey(
        Device, on_delete=models.SET_NULL, null=True, blank=True, related_name="enrollment_token"
    )
    revoked = models.BooleanField(default=False)

    # Chosen once, at token-creation time — the admin already knows which
    # laptop this token is for and who it's going to, so it's copied onto
    # the Device the moment it enrolls instead of needing a second manual
    # assignment step afterward. All optional: a token with none of these
    # set still enrolls a device fine, just without org metadata.
    company = models.ForeignKey(
        Company, on_delete=models.SET_NULL, null=True, blank=True, related_name="enrollment_tokens"
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="enrollment_tokens"
    )
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="enrollment_tokens"
    )
    assigned_employee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="enrollment_tokens"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"EnrollmentToken({self.token_prefix}...)"

    @property
    def is_valid(self) -> bool:
        return not self.revoked and not self.used_at and timezone.now() < self.expires_at

    @staticmethod
    def generate_raw_token() -> str:
        return secrets.token_urlsafe(32)

    @classmethod
    def create_with_token(
        cls,
        *,
        created_by,
        ttl_minutes: int,
        label: str = "",
        company=None,
        branch=None,
        department=None,
        assigned_employee=None,
    ):
        raw_token = cls.generate_raw_token()
        token = cls.objects.create(
            token_hash=make_password(raw_token),
            token_prefix=raw_token[:8],
            label=label,
            created_by=created_by,
            expires_at=timezone.now() + timezone.timedelta(minutes=ttl_minutes),
            company=company,
            branch=branch,
            department=department,
            assigned_employee=assigned_employee,
        )
        return token, raw_token

    def check_token(self, raw_token: str) -> bool:
        return check_password(raw_token, self.token_hash)

    def mark_used(self, device: Device):
        self.used_at = timezone.now()
        self.used_by_device = device
        self.save(update_fields=["used_at", "used_by_device"])


class AgentRelease(models.Model):
    """One uploaded build of the Windows agent .exe. At most one row is
    `is_active` at a time — that's the version every agent's periodic
    version check compares itself against and self-updates to. sha256 is
    computed at save time so the agent can verify the download wasn't
    corrupted or tampered with in transit before it ever executes it."""

    version = models.CharField(max_length=30, unique=True)
    exe_file = models.FileField(upload_to="agent_releases/")
    sha256 = models.CharField(max_length=64, editable=False, blank=True)
    file_size = models.PositiveBigIntegerField(editable=False, default=0)
    is_active = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="agent_releases"
    )
    released_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-released_at"]

    def __str__(self):
        return f"AgentRelease({self.version})"

    def save(self, *args, **kwargs):
        is_new_file = bool(self.exe_file) and not self.sha256
        if is_new_file:
            hasher = hashlib.sha256()
            size = 0
            for chunk in self.exe_file.chunks():
                hasher.update(chunk)
                size += len(chunk)
            self.sha256 = hasher.hexdigest()
            self.file_size = size

        super().save(*args, **kwargs)

        if self.is_active:
            AgentRelease.objects.exclude(pk=self.pk).update(is_active=False)

    @classmethod
    def get_active(cls) -> "AgentRelease | None":
        return cls.objects.filter(is_active=True).first()
