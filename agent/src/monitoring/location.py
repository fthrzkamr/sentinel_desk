"""OS-level location via the Windows Location Service. Windows itself decides
whether to use GPS hardware, Wi-Fi positioning, or nothing at all — this
agent never talks to a GPS chip directly, only what the OS is willing to give
it, and only if Windows' own Location privacy setting allows it. Returns None
if unavailable, denied, or timed out — the server falls back to an IP-based
estimate in that case (see apps/locations/services.py)."""

import asyncio
import logging

logger = logging.getLogger("sentineldesk.agent")


async def _get_os_location_async():
    from winsdk.windows.devices.geolocation import Geolocator

    access_status = await Geolocator.request_access_async()
    logger.debug("Windows location access status: %s", access_status)

    geolocator = Geolocator()
    position = await geolocator.get_geoposition_async()
    coordinate = position.coordinate
    point = coordinate.point.position

    return {
        "latitude": point.latitude,
        "longitude": point.longitude,
        "accuracy_meters": coordinate.accuracy,
    }


def get_os_location() -> dict | None:
    try:
        return asyncio.run(_get_os_location_async())
    except Exception as exc:  # noqa: BLE001 - any failure here just means "no OS location this cycle"
        logger.info("OS location unavailable (%s)", exc)
        return None
