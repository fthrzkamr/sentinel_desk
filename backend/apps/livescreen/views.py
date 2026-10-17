from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasPermission
from apps.devices.models import Device

from . import presence


class LiveScreenStatusView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("monitoring.live_screen")]

    def get(self, request, device_id):
        device = get_object_or_404(Device, device_id=device_id)
        return Response(
            {
                "device_id": device.device_id,
                "device_disabled": device.status == Device.Status.DISABLED,
                "agent_online": presence.is_agent_online(device_id),
                "being_viewed": presence.is_being_viewed(device_id),
            }
        )
