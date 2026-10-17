from rest_framework.permissions import BasePermission


def HasPermission(code: str):
    """Factory for a DRF permission class that checks a granular permission
    code against the authenticated user's role. All permission checks live
    here in the backend — the frontend only uses them to decide what to show,
    never to decide what is allowed."""

    class _HasPermission(BasePermission):
        message = f"Missing required permission: {code}"

        def has_permission(self, request, view):
            user = request.user
            return bool(user and user.is_authenticated and user.has_permission_code(code))

    _HasPermission.__name__ = f"HasPermission_{code.replace('.', '_')}"
    return _HasPermission
