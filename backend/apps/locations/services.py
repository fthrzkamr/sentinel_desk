import ipaddress
import logging

import requests
from django.conf import settings

logger = logging.getLogger("sentineldesk.locations")

# IP geolocation is a city-level estimate at best — there's no real per-request
# radius from the free lookup API, so this is a documented, conservative
# stand-in rather than a fabricated precise number. Never presented as exact.
IP_GEOLOCATION_ACCURACY_METERS = 5000


def estimate_location_from_ip(ip_address: str) -> dict:
    """Best-effort city-level estimate from a public IP. Returns all-None
    fields (never fabricated coordinates) when the IP is private/loopback or
    the lookup fails for any reason — the caller still records the attempt."""

    empty = {"latitude": None, "longitude": None, "accuracy_meters": None}

    if not ip_address:
        return empty

    try:
        ip_obj = ipaddress.ip_address(ip_address)
        if ip_obj.is_private or ip_obj.is_loopback:
            return empty
    except ValueError:
        return empty

    try:
        response = requests.get(
            f"{settings.IP_GEOLOCATION_API_URL}{ip_address}",
            params={"fields": "status,lat,lon"},
            timeout=settings.IP_GEOLOCATION_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("IP geolocation lookup failed for %s: %s", ip_address, exc)
        return empty

    if data.get("status") != "success" or data.get("lat") is None:
        return empty

    return {
        "latitude": data["lat"],
        "longitude": data["lon"],
        "accuracy_meters": IP_GEOLOCATION_ACCURACY_METERS,
    }
