"""Basic security-posture checks (BitLocker, firewall, antivirus) — unlike
hardware_details.py this is collected periodically, not once, since these
can flip off mid-session (a user disabling the firewall matters more than
their motherboard model changing). Every check is independently
try/excepted for the same reason as hardware_details: one missing WMI
namespace (older Windows edition, no AV registered, BitLocker unsupported
on this SKU) shouldn't blank out the other two."""

import logging

logger = logging.getLogger("sentineldesk.agent")


def _bitlocker_status() -> dict:
    """GetProtectionStatus on the OS drive's Win32_EncryptableVolume: 0=off,
    1=on, 2=unknown. Only Pro/Enterprise editions expose this namespace at
    all — Home edition callers land in the except branch, which is reported
    as "unknown" (None) rather than "not encrypted"."""
    try:
        import win32com.client

        wmi_ns = win32com.client.GetObject(r"winmgmts:\\.\root\cimv2\security\MicrosoftVolumeEncryption")
        for volume in wmi_ns.InstancesOf("Win32_EncryptableVolume"):
            if (volume.DriveLetter or "").upper() != "C:":
                continue
            result = volume.GetProtectionStatus()
            # win32com returns (return_code, out_param) for methods with an
            # [out] parameter — ProtectionStatus is the second element.
            status = result[1] if isinstance(result, tuple) else result
            return {"bitlocker_enabled": status == 1}
    except Exception as exc:  # noqa: BLE001 - Home edition, or namespace unavailable
        logger.info("Could not read BitLocker status (%s)", exc)
    return {"bitlocker_enabled": None}


def _firewall_status() -> dict:
    try:
        import win32com.client

        wmi_ns = win32com.client.GetObject(r"winmgmts:\\.\root\StandardCimv2")
        profiles = list(wmi_ns.InstancesOf("MSFT_NetFirewallProfile"))
        if not profiles:
            return {"firewall_enabled": None}
        # "Enabled" if any profile (Domain/Private/Public) is active —
        # matches what Windows Security Center itself shows as the headline
        # firewall state.
        return {"firewall_enabled": any(bool(p.Enabled) for p in profiles)}
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not read firewall status (%s)", exc)
        return {"firewall_enabled": None}


def _decode_av_product_state(product_state: int) -> tuple[bool, bool]:
    """productState's bit layout isn't officially documented by Microsoft.
    This decoding (middle hex byte = enabled/disabled state, last hex byte =
    definitions up-to-date) is the widely-used community-reverse-engineered
    interpretation every open-source AV-status script converges on —
    verified against this machine's real Windows Defender productState
    (0x061100, middle byte "11") cross-checked with Get-MpComputerStatus
    reporting AntivirusEnabled=True: "10" and "11" both mean on, "00"/"01"
    mean off/expired."""
    hex_state = f"{product_state:06x}"
    enabled = hex_state[2:4] in ("10", "11")
    up_to_date = hex_state[4:6] == "00"
    return enabled, up_to_date


def _antivirus_status() -> dict:
    try:
        import win32com.client

        wmi_ns = win32com.client.GetObject(r"winmgmts:\\.\root\SecurityCenter2")
        products = list(wmi_ns.InstancesOf("AntiVirusProduct"))
        if not products:
            return {"antivirus_name": "", "antivirus_enabled": None}
        # Multiple registered products (e.g. Defender + a third-party AV)
        # aren't unusual — report whichever one is actually enabled, falling
        # back to the first entry if none report as enabled.
        for product in products:
            enabled, _ = _decode_av_product_state(int(product.productState))
            if enabled:
                return {"antivirus_name": (product.displayName or "").strip(), "antivirus_enabled": True}
        first = products[0]
        return {"antivirus_name": (first.displayName or "").strip(), "antivirus_enabled": False}
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not read antivirus status (%s)", exc)
        return {"antivirus_name": "", "antivirus_enabled": None}


def gather_compliance_status() -> dict:
    return {
        **_bitlocker_status(),
        **_firewall_status(),
        **_antivirus_status(),
    }
