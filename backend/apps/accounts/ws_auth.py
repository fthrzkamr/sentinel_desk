from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def get_user_from_token(token: str):
    """Shared JWT-over-WebSocket auth for admin-facing consumers. Returns
    None (never raises) on any failure so callers can uniformly reject the
    connection — invalid/expired token, inactive user, all the same result."""
    from .models import User

    if not token:
        return None
    try:
        validated = AccessToken(token)
        user = User.objects.select_related("role").get(pk=validated["user_id"])
    except Exception:  # noqa: BLE001 - any parsing/lookup failure just means "not authenticated"
        return None
    if not user.is_active:
        return None
    # Compute this now, inside the sync DB context — has_permission_code()
    # itself does an ORM query, which is illegal to call later from the
    # consumer's async methods (SynchronousOnlyOperation).
    user.cached_permission_codes = user.permission_codes()
    return user


def user_has_permission(user, code: str) -> bool:
    """Async-safe permission check for a user object returned by
    get_user_from_token — reads the codes cached at fetch time instead of
    touching the ORM again."""
    return code in getattr(user, "cached_permission_codes", ())
