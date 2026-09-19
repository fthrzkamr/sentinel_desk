from rest_framework import serializers

from .models import AgentRelease, Branch, Company, Department, Device, Employee, EnrollmentToken


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
    department_label = serializers.CharField(source="department.__str__", read_only=True, default=None)

    class Meta:
        model = Employee
        fields = ["id", "department", "department_label", "full_name", "email", "position"]


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
    # Plain FK ids alongside the display strings above — the edit form
    # needs these to pre-select the right option in each cascading dropdown,
    # which a human-readable name alone can't do unambiguously.
    company_id = serializers.IntegerField(read_only=True)
    branch_id = serializers.IntegerField(read_only=True)
    department_id = serializers.IntegerField(read_only=True)
    assigned_employee_id = serializers.IntegerField(read_only=True)

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
            "revoked",
            "is_valid",
            "company",
            "branch",
            "department",
            "assigned_employee",
        ]
        read_only_fields = fields


class EnrollmentTokenCreateSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    ttl_minutes = serializers.IntegerField(required=False, min_value=1, max_value=10080)
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
    token = serializers.CharField()
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
    mac_address = serializers.CharField(max_length=17, required=False, allow_blank=True, default="")
    agent_version = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")


class HeartbeatSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    agent_version = serializers.CharField(max_length=30, required=False, allow_blank=True)


class AgentReleaseSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.StringRelatedField()

    class Meta:
        model = AgentRelease
        fields = [
            "id",
            "version",
            "exe_file",
            "sha256",
            "file_size",
            "is_active",
            "notes",
            "uploaded_by",
            "released_at",
        ]
        read_only_fields = ["id", "sha256", "file_size", "uploaded_by", "released_at"]
