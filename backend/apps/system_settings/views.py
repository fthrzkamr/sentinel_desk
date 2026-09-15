from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasPermission
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
