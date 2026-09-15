import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    """DRF's rate-limit throttling stores counters in Django's cache, which
    persists across tests in the same process (unlike the DB, which pytest-
    django rolls back per test). Without this, running the full suite trips
    the login throttle (10/min) since many tests each log in once."""
    cache.clear()
    yield
    cache.clear()
