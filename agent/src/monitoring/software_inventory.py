"""Installed-software inventory via the standard Windows "Uninstall" registry
keys — the same mechanism Control Panel's "Programs and Features" uses. This
never reads user documents or personal files, only install metadata that
every installer already registers for uninstall purposes."""

import winreg
from datetime import datetime

UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]


def _read_value(key, name, default=None):
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return value
    except FileNotFoundError:
        return default


def _parse_install_date(raw):
    if not raw or len(str(raw)) != 8 or not str(raw).isdigit():
        return None
    try:
        return datetime.strptime(str(raw), "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def gather_installed_software() -> list:
    seen = {}

    for hive, path in UNINSTALL_KEYS:
        try:
            root = winreg.OpenKey(hive, path)
        except FileNotFoundError:
            continue

        subkey_count = winreg.QueryInfoKey(root)[0]
        for i in range(subkey_count):
            try:
                subkey_name = winreg.EnumKey(root, i)
                with winreg.OpenKey(root, subkey_name) as subkey:
                    name = _read_value(subkey, "DisplayName")
                    if not name:
                        continue
                    # Skip OS components and update/patch entries — noise,
                    # not something an admin cares about in an inventory.
                    if _read_value(subkey, "SystemComponent", 0) == 1:
                        continue
                    if _read_value(subkey, "ParentKeyName"):
                        continue

                    version = _read_value(subkey, "DisplayVersion", "") or ""
                    publisher = _read_value(subkey, "Publisher", "") or ""
                    install_date = _parse_install_date(_read_value(subkey, "InstallDate", ""))

                    seen[(name, version)] = {
                        "name": name,
                        "version": version,
                        "publisher": publisher,
                        "install_date": install_date,
                    }
            except OSError:
                continue

        root.Close()

    return list(seen.values())
