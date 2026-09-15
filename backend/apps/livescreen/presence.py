"""Tracks the live-screen signaling pairing for each device: at most one
agent connection and one admin viewer at a time. Backed by Django's cache
(Redis) rather than an in-process dict since Channels consumers can run in
any worker process, and a plain dict wouldn't be shared between them."""

from django.core.cache import cache

PRESENCE_TTL_SECONDS = 60


def _agent_key(device_id: str) -> str:
    return f"livescreen:agent_channel:{device_id}"


def _admin_key(device_id: str) -> str:
    return f"livescreen:admin_channel:{device_id}"


def mark_agent_online(device_id: str, channel_name: str):
    cache.set(_agent_key(device_id), channel_name, timeout=PRESENCE_TTL_SECONDS)


def refresh_agent_presence(device_id: str, channel_name: str):
    mark_agent_online(device_id, channel_name)


def mark_agent_offline(device_id: str):
    cache.delete(_agent_key(device_id))


def is_agent_online(device_id: str) -> bool:
    return cache.get(_agent_key(device_id)) is not None


def get_agent_channel(device_id: str):
    return cache.get(_agent_key(device_id))


def mark_admin_viewing(device_id: str, channel_name: str):
    cache.set(_admin_key(device_id), channel_name, timeout=PRESENCE_TTL_SECONDS)


def clear_admin_viewing(device_id: str):
    cache.delete(_admin_key(device_id))


def get_admin_channel(device_id: str):
    return cache.get(_admin_key(device_id))


def is_being_viewed(device_id: str) -> bool:
    return cache.get(_admin_key(device_id)) is not None
