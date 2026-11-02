from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasPermission
from apps.alerts.notifications import dispatch_notification, has_any_channel_configured
from apps.audit.services import log_action

from .models import SystemSettings
from .serializers import SystemSettingsSerializer


class SystemSettingsView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("settings.manage")]

    def get(self, request):
        return Response(SystemSettingsSerializer(SystemSettings.get_solo()).data)

    def patch(self, request):
        instance = SystemSettings.get_solo()
        serializer = SystemSettingsSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        log_action(
            user=request.user,
            action="settings.updated",
            request=request,
            metadata={"changed_fields": list(request.data.keys())},
        )
        return Response(serializer.data)


class TestNotificationView(APIView):
    """Sends a synchronous test message across whichever notification channels
    are configured (either from the request body's unsaved form state or the
    stored SystemSettings solo row) so an admin can verify Telegram/Webhook/
    Email credentials immediately from the Settings page."""

    permission_classes = [IsAuthenticated, HasPermission("settings.manage")]

    def post(self, request):
        config = SystemSettings.get_solo()
        for field in ("telegram_bot_token", "telegram_chat_id", "webhook_url", "notification_emails"):
            if field in request.data and request.data[field] is not None:
                setattr(config, field, str(request.data[field]))

        if not has_any_channel_configured(config):
            return Response(
                {
                    "detail": (
                        "Konfigurasi minimal satu kanal notifikasi (Telegram Bot Token + Chat ID, "
                        "Webhook URL, atau Email Penerima) terlebih dahulu."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = dispatch_notification(
            title="Test Notification",
            body=(
                f"Ini adalah pesan uji coba dari SentinelDesk yang dikirim oleh {request.user.username}. "
                "Kanal notifikasi eksternal Anda sudah berfungsi dengan baik."
            ),
            metadata={"test": True, "triggered_by": request.user.username},
            config=config,
        )

        log_action(
            user=request.user,
            action="settings.test_notification_sent",
            request=request,
            metadata={"sent": result["sent"], "errors": result["errors"]},
        )

        if result["errors"] and not result["sent"]:
            return Response(
                {
                    "detail": "Gagal mengirim pesan tes ke kanal yang dikonfigurasi.",
                    "sent": result["sent"],
                    "errors": result["errors"],
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "detail": f"Pesan tes berhasil dikirim ke: {', '.join(result['sent'])}.",
                "sent": result["sent"],
                "errors": result["errors"],
            },
            status=status.HTTP_200_OK,
        )


class AgentBinaryUploadView(APIView):
    """Allows an administrator to upload a new packaged agent .exe release.
    Automatically computes SHA-256 checksum, saves the file to
    MEDIA_ROOT/agent/, and updates SystemSettings for OTA distribution."""

    permission_classes = [IsAuthenticated, HasPermission("settings.manage")]

    def post(self, request):
        import hashlib
        import os
        from django.conf import settings

        version = request.data.get("version", "").strip()
        uploaded_file = request.FILES.get("file")

        if not version:
            return Response({"detail": "Versi agent wajib diisi (mis. 0.8.16)."}, status=status.HTTP_400_BAD_REQUEST)
        if not uploaded_file:
            return Response({"detail": "File binary agent .exe wajib diunggah."}, status=status.HTTP_400_BAD_REQUEST)

        hasher = hashlib.sha256()
        media_dir = settings.MEDIA_ROOT / "agent"
        os.makedirs(media_dir, exist_ok=True)
        dest_filename = f"SentinelDeskAgent-{version}.exe"
        dest_path = media_dir / dest_filename

        with open(dest_path, "wb") as f:
            for chunk in uploaded_file.chunks():
                hasher.update(chunk)
                f.write(chunk)

        sha256_hex = hasher.hexdigest()
        download_url = f"/api/agent/download/{version}/"

        system_settings = SystemSettings.get_solo()
        system_settings.agent_latest_version = version
        system_settings.agent_sha256 = sha256_hex
        system_settings.agent_download_url = download_url
        system_settings.agent_auto_update_enabled = True
        system_settings.save()

        log_action(
            user=request.user,
            action="agent.release_uploaded",
            request=request,
            metadata={"version": version, "sha256": sha256_hex, "filename": dest_filename},
        )

        return Response(
            {
                "version": version,
                "sha256": sha256_hex,
                "download_url": download_url,
                "auto_update_enabled": True,
            },
            status=status.HTTP_201_CREATED,
        )
