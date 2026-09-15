from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from .models import Device, DeviceCredential


class DeviceUser:
    """Stand-in for request.user on agent-authenticated requests. Not a real
    Django user — agents authenticate with a per-device token, never a user
    account or password."""

    is_authenticated = True
    is_anonymous = False
    pk = None

    def __str__(self):
        return "device"


class DeviceTokenAuthentication(BaseAuthentication):
    """Authenticates SentinelDesk Agent requests using `X-Device-ID` +
    `Authorization: DeviceToken <token>`. On success, `request.auth` is set
    to the Device instance so views can use it directly."""

    keyword = "DeviceToken"

    def authenticate(self, request):
        device_id = request.META.get("HTTP_X_DEVICE_ID")
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if not device_id or not auth_header.startswith(f"{self.keyword} "):
            return None

        raw_token = auth_header[len(self.keyword) + 1 :].strip()
        if not raw_token:
            raise AuthenticationFailed("Missing device token.")

        try:
            device = Device.objects.select_related("credential").get(device_id=device_id)
        except Device.DoesNotExist:
            raise AuthenticationFailed("Unknown device.")

        if device.status == Device.Status.DISABLED:
            raise AuthenticationFailed("Device is disabled.")

        try:
            credential = device.credential
        except DeviceCredential.DoesNotExist:
            raise AuthenticationFailed("Device has no credential.")

        if not credential.check_token(raw_token):
            raise AuthenticationFailed("Invalid device token.")

        credential.touch()
        return (DeviceUser(), device)

    def authenticate_header(self, request):
        return self.keyword


class IsDevice(BasePermission):
    """Restricts a view to requests authenticated via DeviceTokenAuthentication."""

    def has_permission(self, request, view):
        return isinstance(request.auth, Device)
