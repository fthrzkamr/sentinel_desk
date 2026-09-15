from django.http import HttpRequest

from .models import AuditLog


def get_client_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_action(*, user=None, action: str, request: HttpRequest | None = None, device_id=None, metadata=None):
    AuditLog.objects.create(
        user=user,
        action=action,
        device_id=device_id,
        ip_address=get_client_ip(request) if request else None,
        metadata=metadata or {},
    )
