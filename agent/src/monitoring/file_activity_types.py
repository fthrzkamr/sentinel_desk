"""Shared constants for file activity events, kept in one place so the
watcher and the payloads sent to the backend can't drift out of sync with
each other or with the backend's FileActivityEvent.Source choices."""


class Source:
    LOCAL = "LOCAL"
    USB = "USB"
