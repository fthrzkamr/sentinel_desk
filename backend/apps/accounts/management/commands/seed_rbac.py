from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Permission, Role

PERMISSIONS = [
    ("device.view", "View device list and detail"),
    ("device.manage", "Edit device metadata and assignment"),
    ("device.disable", "Disable or re-enable a device"),
    ("monitoring.view", "View realtime metrics and history"),
    ("monitoring.live_screen", "Start/stop live screen monitoring"),
    ("location.view", "View device location and history"),
    ("software.view", "View software inventory"),
    ("alert.view", "View alerts"),
    ("alert.manage", "Acknowledge and resolve alerts"),
    ("agent.manage", "Manage enrollment tokens and agent versions"),
    ("audit.view", "View audit logs"),
    ("user.manage", "Manage users, roles and permissions"),
    ("settings.manage", "Tune system thresholds (CPU/RAM/Disk/Battery, offline detection, retention)"),
]

ROLE_PERMISSIONS = {
    "SUPER_ADMIN": [code for code, _ in PERMISSIONS],
    "IT_ADMIN": [code for code, _ in PERMISSIONS if code != "user.manage"],
    "IT_OPERATOR": [
        "device.view",
        "monitoring.view",
        "monitoring.live_screen",
        "location.view",
        "software.view",
        "alert.view",
        "alert.manage",
        "audit.view",
    ],
    "VIEWER": [
        "device.view",
        "monitoring.view",
        "location.view",
        "software.view",
        "alert.view",
        "audit.view",
    ],
}


class Command(BaseCommand):
    help = "Seed the default SentinelDesk permissions and roles (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        for code, description in PERMISSIONS:
            perm, created = Permission.objects.update_or_create(
                code=code, defaults={"description": description}
            )
            self.stdout.write(f"{'created' if created else 'ok'}: permission {code}")

        for role_name, codes in ROLE_PERMISSIONS.items():
            role, created = Role.objects.get_or_create(name=role_name)
            role.permissions.set(Permission.objects.filter(code__in=codes))
            self.stdout.write(f"{'created' if created else 'updated'}: role {role_name}")

        self.stdout.write(self.style.SUCCESS("RBAC seed complete."))
