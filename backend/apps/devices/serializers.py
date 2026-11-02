from rest_framework import serializers

from .models import Asset, Branch, Company, Department, Device, Employee, EnrollmentToken


class AssetSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True, default=None)
    device_hostname = serializers.CharField(source="device.hostname", read_only=True, default=None)
    assigned_employee = serializers.CharField(source="device.assigned_employee", read_only=True, default=None)
    branch = serializers.CharField(source="device.branch", read_only=True, default=None)
    # The matcher's best guess for a NEEDS_REVIEW row (see
    # Asset.suggested_device) - a real name/laptop for the admin to
    # confirm-or-reject, instead of only the raw asset_dfm text + a bare
    # confidence number.
    suggested_device_id = serializers.CharField(source="suggested_device.device_id", read_only=True, default=None)
    suggested_device_hostname = serializers.CharField(
        source="suggested_device.hostname", read_only=True, default=None
    )
    suggested_employee = serializers.CharField(
        source="suggested_device.assigned_employee", read_only=True, default=None
    )
    # The actual, admin-editable "who's using this" - see
    # Asset.current_employee's docstring. Independent of device/
    # suggested_device above, which are about SentinelDesk device-linking
    # specifically and need that laptop to be enrolled; this works for any
    # asset regardless.
    current_employee_id = serializers.IntegerField(source="current_employee.id", read_only=True, default=None)
    current_employee = serializers.StringRelatedField()

    class Meta:
        model = Asset
        fields = [
            "id",
            "asset_code",
            "kondisi",
            "status_barang",
            "raw_penanggung_jawab",
            "raw_lokasi",
            "nama_aset",
            "merk",
            "spesifikasi",
            "lokasi_detail",
            "device_id",
            "device_hostname",
            "assigned_employee",
            "branch",
            "suggested_device_id",
            "suggested_device_hostname",
            "suggested_employee",
            "current_employee_id",
            "current_employee",
            "user_status",
            "match_status",
            "match_confidence",
            "synced_at",
            "created_at",
        ]
        read_only_fields = fields


class AssetSetUserSerializer(serializers.Serializer):
    employee_id = serializers.PrimaryKeyRelatedField(
        source="employee", queryset=Employee.objects.all(), allow_null=True
    )


class AssetSyncSerializer(serializers.Serializer):
    """What asset_dfm's own API is expected to POST per asset - see
    asset_matching.sync_asset() for how each field is used. kondisi/
    status_barang choices mirror that system's enum verbatim so nothing
    needs translating on either side."""

    asset_code = serializers.RegexField(r"^\d{3}-\d{5}-\d{2}$", max_length=100)
    kondisi = serializers.ChoiceField(choices=Asset.Condition.choices, default=Asset.Condition.BAIK)
    status_barang = serializers.ChoiceField(choices=Asset.StatusBarang.choices, default=Asset.StatusBarang.ASSET)
    penanggung_jawab = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    lokasi = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    nama_aset = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    merk = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    spesifikasi = serializers.CharField(required=False, allow_blank=True, default="")
    lokasi_detail = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")


class AssetLinkSerializer(serializers.Serializer):
    device_id = serializers.SlugRelatedField(
        slug_field="device_id", queryset=Device.objects.all(), allow_null=True
    )


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "created_at"]
        read_only_fields = ["id", "created_at"]


class BranchSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Branch
        fields = ["id", "company", "company_name", "name"]


class DepartmentSerializer(serializers.ModelSerializer):
    branch_label = serializers.CharField(source="branch.__str__", read_only=True)

    class Meta:
        model = Department
        fields = ["id", "branch", "branch_label", "name"]


class EmployeeSerializer(serializers.ModelSerializer):
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    branch_id = serializers.IntegerField(source="department.branch.id", read_only=True, default=None)
    branch_name = serializers.CharField(source="department.branch.name", read_only=True, default=None)
    company_id = serializers.IntegerField(source="department.branch.company.id", read_only=True, default=None)
    company_name = serializers.CharField(source="department.branch.company.name", read_only=True, default=None)
    department_label = serializers.CharField(source="department.__str__", read_only=True, default=None)

    class Meta:
        model = Employee
        fields = [
            "id",
            "department",
            "department_name",
            "branch_id",
            "branch_name",
            "company_id",
            "company_name",
            "department_label",
            "full_name",
            "email",
            "position",
        ]


class DeviceAssetSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ["asset_code", "kondisi", "status_barang", "match_status"]


class DeviceSerializer(serializers.ModelSerializer):
    company = serializers.StringRelatedField()
    # Branch/Department's __str__ is the full "Company / Branch[ / Dept]"
    # chain (see Branch/Department.__str__) — needed as-is for compact
    # single-line displays elsewhere (device lists, alerts, map popups) that
    # show org context without a separate Company field nearby. Also expose
    # the bare .name so a view that already shows Company/Branch/Department
    # as separate labeled fields (Device Detail's Overview tab) doesn't
    # repeat the parent chain in every child field.
    branch = serializers.StringRelatedField()
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    department = serializers.StringRelatedField()
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    assigned_employee = serializers.StringRelatedField()
    # Null when no asset_dfm record has been synced/linked to this device
    # yet - a device never has its own asset_code anymore (see Asset's
    # docstring for why that moved out of Device entirely). `device` is a
    # plain ForeignKey on Asset now, not OneToOne (one device can legitimately
    # have more than one linked laptop-category asset over time - a
    # replacement issued, the old one not yet retired in asset_dfm), so
    # this picks the most recently synced one rather than an ORM accessor
    # that no longer exists as a single object.
    asset = serializers.SerializerMethodField()

    def get_asset(self, device):
        # .all() (not .order_by(...)) so this hits the prefetch_related
        # cache set up by the view's queryset instead of firing a fresh
        # query per device - Asset's own Meta.ordering (-synced_at) already
        # applies by default, so the first item here is still the latest.
        assets = list(device.assets.all())
        return DeviceAssetSummarySerializer(assets[0]).data if assets else None
    # Plain FK ids alongside the display strings above — the edit form
    # needs these to pre-select the right option in each cascading dropdown,
    # which a human-readable name alone can't do unambiguously.
    company_id = serializers.IntegerField(read_only=True)
    branch_id = serializers.IntegerField(read_only=True)
    department_id = serializers.IntegerField(read_only=True)
    assigned_employee_id = serializers.IntegerField(read_only=True)
    battery_health_percent = serializers.FloatField(read_only=True)

    class Meta:
        model = Device
        fields = [
            "id",
            "device_id",
            "hostname",
            "computer_name",
            "username",
            "os_name",
            "os_version",
            "architecture",
            "cpu",
            "ram",
            "disk",
            "serial_number",
            "manufacturer",
            "model",
            "system_family",
            "cpu_cores",
            "cpu_threads",
            "cpu_speed_mhz",
            "motherboard",
            "bios_version",
            "gpu_details",
            "ram_details",
            "disk_details",
            "battery_design_capacity_mwh",
            "battery_full_charge_capacity_mwh",
            "battery_health_percent",
            "bitlocker_enabled",
            "firewall_enabled",
            "antivirus_name",
            "antivirus_enabled",
            "mac_address",
            "ip_address",
            "agent_version",
            "status",
            "last_seen",
            "first_registered",
            "company",
            "company_id",
            "branch_id",
            "department_id",
            "assigned_employee_id",
            "branch",
            "branch_name",
            "department",
            "department_name",
            "assigned_employee",
            "is_approved",
            "asset",
        ]
        read_only_fields = fields


class DeviceOrgAssignmentSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all(), required=False, allow_null=True)
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all(), required=False, allow_null=True)
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    assigned_employee = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Device
        fields = ["company", "branch", "department", "assigned_employee"]


class EnrollmentTokenSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField()
    used_by_device = serializers.SlugRelatedField(slug_field="device_id", read_only=True)
    # Display label for the UI's "Device" column - asset_code when that
    # device has one synced from asset_dfm (the identifier admins actually
    # recognize), falling back to hostname rather than the raw device_id.
    used_by_device_label = serializers.SerializerMethodField()
    is_valid = serializers.BooleanField(read_only=True)
    company = serializers.StringRelatedField()
    branch = serializers.StringRelatedField()
    department = serializers.StringRelatedField()
    assigned_employee = serializers.StringRelatedField()

    class Meta:
        model = EnrollmentToken
        fields = [
            "id",
            "token_prefix",
            "label",
            "created_by",
            "created_at",
            "expires_at",
            "used_at",
            "used_by_device",
            "used_by_device_label",
            "revoked",
            "is_valid",
            "is_reusable",
            "use_count",
            "company",
            "branch",
            "department",
            "assigned_employee",
        ]
        read_only_fields = fields

    def get_used_by_device_label(self, obj):
        device = obj.used_by_device
        if not device:
            return None
        asset = device.assets.first()
        return asset.asset_code if asset else device.hostname


class EnrollmentTokenCreateSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    # 525600 = 365 days. A normal one-laptop token only ever needs an hour
    # or two, but a *reusable* deployment key baked into an MSI installer
    # (see is_reusable below) is meant to stay valid for as long as that
    # MSI stays in use across a whole fleet - the old 10080 (7-day) cap
    # forced a token rotation + MSI rebuild on a schedule that had nothing
    # to do with security, just an arbitrary limit. Security for a
    # long-lived reusable key comes from the Pending Approval gate (see
    # Device.is_approved) and from being able to revoke it immediately if
    # the installer file ever leaks - not from a short expiry.
    # 525600 min (365 days) was the old ceiling - too short for a reusable
    # deployment key baked into an MSI meant to keep working for years
    # without anyone coming back to regenerate it. Raised to ~10 years;
    # still a real ceiling (not unlimited) since this is the same
    # leaked-file-is-a-standing-risk tradeoff the Pending-Approval gate on
    # reusable tokens already exists to absorb (see Device.is_approved) -
    # a stale/no-longer-wanted key should still be revoked by hand, not
    # relied on to expire itself.
    ttl_minutes = serializers.IntegerField(required=False, min_value=1, max_value=5_256_000)
    # A reusable token stays valid across many devices instead of being
    # spent by the first one — see EnrollmentToken.is_reusable. Meant for
    # baking into the MSI installer for mass deployment, not for a normal
    # one-laptop-at-a-time token.
    is_reusable = serializers.BooleanField(default=False)
    # All optional — copied onto the Device the moment it enrolls with this
    # token (see AgentEnrollView), so the admin can pre-assign a laptop to
    # its company/branch/department/employee right when generating the
    # token instead of editing the device afterward.
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all(), required=False, allow_null=True)
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all(), required=False, allow_null=True)
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    assigned_employee = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(), required=False, allow_null=True
    )


class EnrollRequestSerializer(serializers.Serializer):
    token = serializers.CharField(required=False, allow_blank=True, default="")
    hostname = serializers.CharField(max_length=150)
    computer_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    username = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    os_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    os_version = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    architecture = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    cpu = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    ram = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    disk = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    serial_number = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    manufacturer = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    model = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    system_family = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    mac_address = serializers.CharField(max_length=17, required=False, allow_blank=True, default="")
    agent_version = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    cpu_cores = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=0)
    cpu_threads = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=0)
    cpu_speed_mhz = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=0)
    motherboard = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    bios_version = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    gpu_details = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    ram_details = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    disk_details = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    battery_design_capacity_mwh = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=0)
    battery_full_charge_capacity_mwh = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=0
    )


class HeartbeatSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    agent_version = serializers.CharField(max_length=30, required=False, allow_blank=True)
