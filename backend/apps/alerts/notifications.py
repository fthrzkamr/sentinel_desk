import logging
import urllib.error
import urllib.request
import json

from django.conf import settings
from django.core.mail import send_mail

from apps.system_settings.models import SystemSettings

logger = logging.getLogger("sentineldesk.alerts")

NOTIFICATION_TIMEOUT_SECONDS = 10


def _post_json(url: str, payload: dict, timeout: int = NOTIFICATION_TIMEOUT_SECONDS) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "SentinelDesk-Notifier/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL is admin-configured in SystemSettings
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status}")


def parse_recipient_emails(raw_emails: str) -> list[str]:
    if not raw_emails:
        return []
    return [addr.strip() for addr in raw_emails.split(",") if addr.strip()]


def has_any_channel_configured(config: SystemSettings) -> bool:
    has_telegram = bool(config.telegram_bot_token.strip() and config.telegram_chat_id.strip())
    has_webhook = bool(config.webhook_url.strip())
    has_email = bool(parse_recipient_emails(config.notification_emails))
    return has_telegram or has_webhook or has_email


def dispatch_notification(
    *,
    title: str,
    body: str,
    metadata: dict | None = None,
    config: SystemSettings | None = None,
) -> dict:
    """Sends a notification across all configured external channels (Telegram,
    Webhook, Email). Returns `{"sent": [...], "errors": {...}}` so both the
    background Celery task and the synchronous Test Notification endpoint can
    inspect per-channel outcomes."""
    cfg = config or SystemSettings.get_solo()
    sent: list[str] = []
    errors: dict[str, str] = {}

    full_text = f"🚨 [SentinelDesk] {title}\n\n{body}"

    # 1. Telegram Bot API (plain text on purpose so underscores/brackets in
    #    device IDs, file paths, or URLs never fail Telegram entity parsing).
    bot_token = cfg.telegram_bot_token.strip()
    chat_id = cfg.telegram_chat_id.strip()
    if bot_token and chat_id:
        tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        try:
            _post_json(tg_url, {"chat_id": chat_id, "text": full_text})
            sent.append("telegram")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram notification failed: %s", exc)
            errors["telegram"] = str(exc)

    # 2. Webhook (includes both `text` for Slack/Teams/Mattermost and
    #    `content` for Discord out of the box, plus structured fields).
    webhook_url = cfg.webhook_url.strip()
    if webhook_url:
        try:
            _post_json(
                webhook_url,
                {
                    "text": full_text,
                    "content": full_text,
                    "title": title,
                    "message": body,
                    "metadata": metadata or {},
                },
            )
            sent.append("webhook")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Webhook notification failed: %s", exc)
            errors["webhook"] = str(exc)

    # 3. Email (SMTP / configured Django email backend)
    recipients = parse_recipient_emails(cfg.notification_emails)
    if recipients:
        try:
            send_mail(
                subject=f"[SentinelDesk] {title}",
                message=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@sentineldesk.local"),
                recipient_list=recipients,
                fail_silently=False,
            )
            sent.append("email")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Email notification failed: %s", exc)
            errors["email"] = str(exc)

    return {"sent": sent, "errors": errors}


def format_alert_notification(alert) -> tuple[str, str, dict]:
    device = alert.device
    employee_name = str(device.assigned_employee) if device.assigned_employee else "-"
    branch_name = device.branch.name if device.branch else "-"
    title = f"CRITICAL Alert ({alert.get_category_display()}) — {device.device_id}"
    body = (
        f"Perangkat : {device.device_id} ({device.hostname})\n"
        f"Karyawan  : {employee_name}\n"
        f"Cabang    : {branch_name}\n"
        f"Kategori  : {alert.get_category_display()} [{alert.severity}]\n"
        f"Pesan     : {alert.message}"
    )
    meta = {
        "alert_id": alert.id,
        "device_id": device.device_id,
        "hostname": device.hostname,
        "employee": employee_name,
        "branch": branch_name,
        "category": alert.category,
        "severity": alert.severity,
        "message": alert.message,
    }
    return title, body, meta

