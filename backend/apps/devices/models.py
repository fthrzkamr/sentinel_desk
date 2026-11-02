import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

# Matches the company's existing physical-asset system (asset_dfm):
# {3-digit category code}-{2-digit year}{3-digit sequence}-{2-digit branch
# code}, e.g. "302-25001-01" (302=Laptop, 2025, #001, 01=Jakarta). Used by
# Asset.asset_code (synced in from asset_dfm) and AssetSyncSerializer so a
# malformed code is rejected at the door either way it can arrive.
ASSET_CODE_VALIDATOR = RegexValidator(
    regex=r"^\d{3}-\d{5}-\d{2}$",
    message="Format Asset Code harus mengikuti pola asset_dfm: 302-25001-01 (kategori-tahun+urutan-lokasi).",
)


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

    # False only for a device that enrolled via a *reusable* EnrollmentToken
    # (see that model below) — a single-use token still auto-approves
    # immediately, unchanged from before this field existed. Enforced at
    # the authentication layer (DeviceTokenAuthentication.authenticate())
    # so every agent-facing endpoint is blocked for a pending device with
    # one check, not one per view.
    is_approved = models.BooleanField(default=True)

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
    # The manufacturer's own MTM/part code ("20T3S2WY00" on Lenovo) - not
    # human-readable, not comparable to anything an asset_dfm data-entry
    # person would type. See system_family for the actual marketing name.
    model = models.CharField(max_length=150, blank=True)
    # WMI's Win32_ComputerSystem.SystemFamily - the marketing name printed
    # on the laptop itself ("ThinkPad X13 Gen 1"), unlike `model` above.
    # Not every OEM populates this field, so it's often blank - kept
    # separate rather than replacing `model`.
    system_family = models.CharField(max_length=150, blank=True)

    # Detailed spec snapshot, collected once at enrollment via WMI (see
    # agent/src/monitoring/hardware_details.py) — everything above this is
    # the original Phase-1 identity/capacity summary; these fill in what a
    # real spec sheet needs on top of that. All optional: any WMI class that
    # a given machine doesn't expose (VMs, older BIOS, etc.) just leaves its
    # field blank rather than failing enrollment.
    cpu_cores = models.PositiveSmallIntegerField(null=True, blank=True)
    cpu_threads = models.PositiveSmallIntegerField(null=True, blank=True)
    cpu_speed_mhz = models.PositiveIntegerField(null=True, blank=True)
    motherboard = models.CharField(max_length=200, blank=True)
    bios_version = models.CharField(max_length=100, blank=True)
    # Each: [{"name": "NVIDIA GeForce RTX 3050", "driver_version": "31.0.15...", "vram_mb": 4096}]
    gpu_details = models.JSONField(default=list, blank=True)
    # Each: [{"capacity_gb": 8, "speed_mhz": 3200, "manufacturer": "SK Hynix", "slot": "DIMM 0"}]
    ram_details = models.JSONField(default=list, blank=True)
    # Each: [{"model": "Samsung SSD 970 EVO", "size_gb": 500, "media_type": "SSD"}]
    disk_details = models.JSONField(default=list, blank=True)
    battery_design_capacity_mwh = models.PositiveIntegerField(null=True, blank=True)
    battery_full_charge_capacity_mwh = models.PositiveIntegerField(null=True, blank=True)

    # Basic security-posture snapshot, re-checked hourly by the agent (see
    # agent/src/monitoring/compliance.py) — null means "not yet checked" or
    # "couldn't be determined" (e.g. BitLocker on a Home edition), not "off".
    bitlocker_enabled = models.BooleanField(null=True, blank=True)
    firewall_enabled = models.BooleanField(null=True, blank=True)
    antivirus_name = models.CharField(max_length=150, blank=True)
    antivirus_enabled = models.BooleanField(null=True, blank=True)

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

    @property
    def battery_health_percent(self) -> float | None:
        if not self.battery_design_capacity_mwh or not self.battery_full_charge_capacity_mwh:
            return None
        return round(self.battery_full_charge_capacity_mwh / self.battery_design_capacity_mwh * 100, 1)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        # If assigned_employee is set, cascade department/branch/company if missing
        if self.assigned_employee_id and self.assigned_employee:
            emp = self.assigned_employee
            dept = emp.department
            if dept:
                fields_to_add = []
                if not self.department_id:
                    self.department = dept
                    fields_to_add.append("department")
                if not self.branch_id and dept.branch:
                    self.branch = dept.branch
                    fields_to_add.append("branch")
                if not self.company_id and dept.branch and dept.branch.company:
                    self.company = dept.branch.company
                    fields_to_add.append("company")

                update_fields = kwargs.get("update_fields")
                if update_fields is not None and fields_to_add:
                    kwargs["update_fields"] = list(set(update_fields) | set(fields_to_add))

        super().save(*args, **kwargs)
        if is_new and not self.device_id:
            self.device_id = f"SD-LPT-{self.pk:06d}"
            super().save(update_fields=["device_id"])

    def mark_seen(self):
        self.last_seen = timezone.now()
        if self.status != Device.Status.DISABLED:
            self.status = Device.Status.ONLINE
        self.save(update_fields=["last_seen", "status"])


class Asset(models.Model):
    """A physical-asset record synced in from the company's separate
    asset_dfm system (see devices/asset_matching.py for the sync endpoint
    and auto-link logic) — deliberately NOT a full mirror of that system's
    schema. Only the fields asset_dfm is the actual source of truth for
    (the asset code itself, physical condition, owned-vs-rented status) are
    kept here; who's using it is tracked more reliably by SentinelDesk
    itself via `device`/`current_employee` once that's known, so this links
    to that instead of duplicating guesswork. `raw_*` fields are the
    untouched text asset_dfm sent, kept only as the input the matcher used
    and for an admin reviewing a low-confidence match to see what it was
    working from — never shown as "the" assigned person/branch, which is
    always `device.assigned_employee`/`device.branch` once linked.

    `nama_aset`/`merk`/`spesifikasi`/`lokasi_detail` below ARE a plain
    display-only mirror of asset_dfm's own columns, unlike the fields
    above - these exist specifically so an admin can identify a physical
    laptop (brand, specs, exact location) for an asset whose laptop hasn't
    had SentinelDesk installed yet at all, where there's no `device` to
    pull any of that from instead."""

    class Condition(models.TextChoices):
        # Matches asset_dfm's own `kondisi` enum values verbatim, so the
        # sync payload never needs translating on either side.
        BAIK = "Baik", "Baik"
        RUSAK_RINGAN = "Rusak Ringan", "Rusak Ringan"
        RUSAK_BERAT = "Rusak Berat", "Rusak Berat"
        HILANG = "Hilang", "Hilang"
        DIHAPUS = "Dihapus", "Dihapus"

    class StatusBarang(models.TextChoices):
        ASSET = "Asset", "Asset"
        SEWA = "Sewa", "Sewa"

    class MatchStatus(models.TextChoices):
        AUTO_MATCHED = "AUTO_MATCHED", "Auto-matched"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Perlu Dicocokkan"
        LINKED_MANUALLY = "LINKED_MANUALLY", "Ditautkan Manual"
        UNLINKED = "UNLINKED", "Belum Tertaut"

    class UserStatus(models.TextChoices):
        # Auto-classified by asset_matching.classify_user() - see its
        # docstring. Purely about `current_employee` below, independent of
        # MatchStatus above (which is about device-linking specifically).
        IDENTIFIED = "IDENTIFIED", "Teridentifikasi"
        NEEDS_EMPLOYEE = "NEEDS_EMPLOYEE", "Nama Ada, Belum Terdaftar"
        INCOMPLETE = "INCOMPLETE", "Data Belum Lengkap"
        PENDING = "PENDING", "Belum Diproses"

    asset_code = models.CharField(max_length=100, unique=True, validators=[ASSET_CODE_VALIDATOR])
    kondisi = models.CharField(max_length=20, choices=Condition.choices, default=Condition.BAIK)
    status_barang = models.CharField(max_length=10, choices=StatusBarang.choices, default=StatusBarang.ASSET)

    # Exactly what asset_dfm sent for "who holds this" / "which branch" -
    # see the class docstring on why these are reference-only, not display.
    raw_penanggung_jawab = models.CharField(max_length=150, blank=True)
    raw_lokasi = models.CharField(max_length=100, blank=True)

    # Plain display fields mirrored from asset_dfm - see the class
    # docstring above. Blank when asset_dfm sent nothing for them (older
    # sync payloads before these were added, or the field was empty there).
    nama_aset = models.CharField(max_length=150, blank=True)
    merk = models.CharField(max_length=100, blank=True)
    spesifikasi = models.TextField(blank=True)
    lokasi_detail = models.CharField(max_length=150, blank=True)

    # The actual "who's using this asset right now" field - set directly by
    # an admin picking a real Employee, completely independent of `device`/
    # `suggested_device` below. Deliberately decoupled: linking to a Device
    # needs that laptop to have SentinelDesk actually installed, which for
    # most of this fleet hasn't happened yet (see asset_matching.py) - this
    # field works immediately for ANY asset, laptop-enrolled or not, and is
    # the one place a laptop swap between employees gets recorded: admin
    # just repoints this to the new holder, no re-sync or re-matching
    # needed. Auto-filled once from a confident AUTO_MATCHED result as a
    # convenience (see sync_asset) but never overwritten after that by a
    # later sync - an admin's own edit here always wins.
    current_employee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # What classify_user() (asset_matching.py) concluded about
    # raw_penanggung_jawab: a real name it could (IDENTIFIED) or couldn't
    # (NEEDS_EMPLOYEE - no matching Employee record exists yet) resolve, or
    # text that isn't a person at all (INCOMPLETE - a department/role label
    # like "IT" or "Sales Surabaya"). Never overwritten once current_employee
    # is set manually, same rule as current_employee itself.
    user_status = models.CharField(
        max_length=20, choices=UserStatus.choices, default=UserStatus.PENDING
    )

    # ForeignKey, not OneToOne: asset_dfm tracks every asset category (PC,
    # monitor, printer, UPS, ...) for the same employee under the same
    # `user` text, and even laptop-only, one employee can have more than one
    # over time (a replacement issued, the old one not yet retired in
    # asset_dfm). AssetSyncView only processes "302-" (Laptop) codes - see
    # its docstring - but even scoped to just laptops, a OneToOneField here
    # would raise an IntegrityError the moment a second asset ever matched
    # the same already-linked device.
    device = models.ForeignKey(
        Device, on_delete=models.SET_NULL, null=True, blank=True, related_name="assets"
    )
    # The matcher's best guess even when it scored below AUTO_MATCH_THRESHOLD
    # (NEEDS_REVIEW) - never the confirmed link itself (that's `device`).
    # Lets the admin see a real name/laptop to confirm-or-reject on the
    # Assets page instead of searching a blank device dropdown from
    # scratch. No related_name/uniqueness: several low-confidence assets
    # can legitimately all point at the same suggested device at once.
    suggested_device = models.ForeignKey(
        Device, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    match_status = models.CharField(
        max_length=20, choices=MatchStatus.choices, default=MatchStatus.UNLINKED
    )
    # 0-1, how confident the auto-matcher was in `device` (or in
    # `suggested_device`, for a NEEDS_REVIEW row) - null when the link (if
    # any) was set manually instead of by the matcher, or when no candidate
    # scored above 0 at all (UNLINKED with no suggestion either).
    match_confidence = models.FloatField(null=True, blank=True)

    synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-synced_at"]

    def __str__(self):
        return self.asset_code


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
    # A reusable token (a mass-deployment "site key", typically baked into
    # the MSI installer — see agent/installer/Product.wxs) never gets
    # "spent" by use_at like a normal single-use token does; use_count
    # tracks how many devices have enrolled with it instead. Every device
    # it enrolls starts unapproved (Device.is_approved=False) — see
    # AgentEnrollView — since a leaked copy of the installer would
    # otherwise let anyone self-enroll a fully-trusted device unnoticed.
    is_reusable = models.BooleanField(default=False)
    use_count = models.PositiveIntegerField(default=0)

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
        return (
            not self.revoked
            and (self.is_reusable or not self.used_at)
            and timezone.now() < self.expires_at
        )

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
        is_reusable: bool = False,
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
            is_reusable=is_reusable,
        )
        return token, raw_token

    def check_token(self, raw_token: str) -> bool:
        return check_password(raw_token, self.token_hash)

    def mark_used(self, device: Device):
        self.used_by_device = device
        self.use_count = models.F("use_count") + 1
        update_fields = ["used_by_device", "use_count"]
        if not self.is_reusable:
            self.used_at = timezone.now()
            update_fields.append("used_at")
        self.save(update_fields=update_fields)
        self.refresh_from_db(fields=["use_count"])
