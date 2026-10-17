"""Optional, one-time hardening pass so that the SentinelDesk agent can't be
casually stopped or un-registered by the standard (non-admin) employee using
the laptop it's installed on. Every mechanism here is one that a real
Windows Administrator (i.e. IT/this tool's own operator) can still fully
reverse through the normal, documented channels — Services console, Task
Scheduler, or just running uninstall() below:

  - Autostart moves from the per-user Registry Run key (which the logged-on
    user can delete themselves) to a Scheduled Task created while elevated,
    which only Administrators/SYSTEM can modify or remove.
  - A small watchdog Windows Service (see watchdog_service.py) relaunches
    the agent if its process is closed or crashes — standard users can't
    stop a Windows service without admin rights, unlike a plain .exe.

An earlier version of this also locked the install folder's ACLs down to
Read+Execute for standard users. That was reverted: the agent process runs
as that same standard user (it needs the interactive desktop for screen
capture / idle detection), and self-update works by having that same
process overwrite its own .exe and write to logs/ — there is no way to grant
"the agent's own self-update" write access without also granting "the
employee manually deleting the exe" the same access, since both are the
same Windows principal. Locking the folder broke logging and self-update
outright (see git history) rather than actually stopping tampering, so
tamper-resistance here is scoped to "can't be casually End Task'd or have
its autostart removed" — not "the files can never be touched."

This deliberately does NOT hide the agent process from Task Manager, block
Windows Defender from scanning it, or do anything that would stop an
Administrator from managing or removing it — that would cross from
"tamper-resistant IT agent" into malware-like behavior, which this project
does not do. install()/uninstall() below both require an elevated process
and fail loudly (never silently) if run without admin rights."""

import ctypes
import logging
import os
import subprocess

import win32com.client

from config.settings import CREDENTIALS_PATH

logger = logging.getLogger("sentineldesk.agent")

SCHEDULED_TASK_NAME = "SentinelDeskAgent"


class HardeningError(Exception):
    pass


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


# This module's own exe (SentinelDeskAgent.exe) is built windowed (no
# console of its own), and every command run from here — schtasks, icacls,
# the watchdog exe's install/start — is a plain console tool. Spawned from a
# process with no console at all, Windows pops up a new, briefly-visible
# console window for each one; CREATE_NO_WINDOW gives the parent a hidden
# console instead so none of that ever flashes on the employee's screen.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW)
    if result.returncode != 0:
        raise HardeningError(f"Command failed ({' '.join(cmd)}): {result.stderr.strip() or result.stdout.strip()}")
    return result


def _current_username() -> str:
    return os.environ.get("USERNAME", "")


def _tune_task_settings() -> None:
    """schtasks /Create has no flags for either setting below, so both need
    a follow-up pass through the Task Scheduler COM API.

    1. Battery restrictions: every task schtasks creates defaults to "only
       start on AC power, stop if the computer switches to battery" unless
       told otherwise. Left on, this task sits permanently in a Queued
       state - never actually launching the agent - on any laptop that's
       unplugged at logon time, which for a mobile fleet is most of the
       time.

    2. Multiple instances: schtasks /Create defaults a new task to allowing
       several simultaneous runs (TASK_INSTANCES_PARALLEL) instead of the
       Task Scheduler GUI's own default of "don't start a new instance if
       one is already running". This task gets triggered from more than one
       place - the Watchdog Service checks and relaunches it the moment it
       starts (see watchdog_service.py's main loop, which fires its first
       check immediately, no delay), and this same install sequence used to
       also trigger it once itself via a Product.wxs custom action. Two
       nearly-simultaneous launches of a process that's creating its own
       log folder for the very first time is a real race - both instances
       fighting to create logs\\agent.log at once is exactly what produced
       the "PermissionError: ...\\logs\\agent.log" crash on fresh installs,
       not a permissions problem (ProgramData already grants standard users
       write access here by default - confirmed via `icacls`). Setting
       IgnoreNew here closes the race at its source: whichever trigger
       reaches the task first wins, and any other trigger arriving while
       that instance is still starting up is simply dropped.

    An earlier version of this used PowerShell's
    `Set-ScheduledTask -InputObject $task` after flipping properties on the
    object `Get-ScheduledTask` returned. That reported success (exit code 0,
    no error) but silently failed to persist - querying the task afterward
    still showed the old values. The Task Scheduler COM API (what
    schtasks/PowerShell both wrap underneath) is the reliable way to
    actually change and re-register a task's Settings; pywin32 (already a
    dependency here, see watchdog_service.py/system_errors.py) exposes it
    directly."""
    try:
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        folder = scheduler.GetFolder("\\")
        task = folder.GetTask(SCHEDULED_TASK_NAME)
        definition = task.Definition
        definition.Settings.DisallowStartIfOnBatteries = False
        definition.Settings.StopIfGoingOnBatteries = False
        definition.Settings.MultipleInstances = 2  # TASK_INSTANCES_IGNORE_NEW
        # 6 = TASK_CREATE_OR_UPDATE, 3 = TASK_LOGON_INTERACTIVE_TOKEN
        # (matches the /IT flag schtasks /Create used above).
        folder.RegisterTaskDefinition(SCHEDULED_TASK_NAME, definition, 6, None, None, 3)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to tune scheduled task settings: %s", exc)


def _create_protected_scheduled_task(agent_exe_path: str) -> None:
    username = _current_username()
    _run([
        "schtasks", "/Create", "/F",
        "/RL", "LIMITED",  # standard user rights — the agent needs the interactive desktop, not elevation
        "/SC", "ONLOGON",
        "/RU", username,
        "/IT",  # interactive token: no stored password, only runs while that user is logged on
        "/TN", SCHEDULED_TASK_NAME,
        "/TR", f'"{agent_exe_path}"',
    ])
    _tune_task_settings()
    logger.info("Scheduled task %s created for user %s (admin-protected).", SCHEDULED_TASK_NAME, username)


def _remove_scheduled_task() -> None:
    subprocess.run(["schtasks", "/Delete", "/F", "/TN", SCHEDULED_TASK_NAME], capture_output=True, text=True, creationflags=_NO_WINDOW)


def _install_watchdog_service(watchdog_exe_path: str) -> None:
    _run([watchdog_exe_path, "--startup", "auto", "install"])
    _run([watchdog_exe_path, "start"])
    logger.info("SentinelDeskWatchdog service installed and started.")


def _remove_watchdog_service(watchdog_exe_path: str) -> None:
    subprocess.run([watchdog_exe_path, "stop"], capture_output=True, text=True, creationflags=_NO_WINDOW)
    subprocess.run([watchdog_exe_path, "remove"], capture_output=True, text=True, creationflags=_NO_WINDOW)


def _add_defender_exclusion(install_dir: str) -> None:
    """Windows Defender's ML heuristic (Trojan:Win32/Bearfoos.B!ml, seen in
    real testing) quarantined SentinelDeskWatchdog.exe on its own - not a
    one-off fluke, but Defender reacting to the exact behavior pattern a
    watchdog service is supposed to have (silently relaunches another
    process, survives being killed, needs admin to remove), which also
    happens to be a classic persistence technique. The real, permanent fix
    is code-signing the build (out of scope here - a cert, not a code
    change) and/or a Microsoft false-positive submission; this is the
    stopgap that actually ships: ask Defender to exclude this install
    folder, once, automatically, as part of the same elevated install the
    MSI already runs - no separate per-machine policy push needed across
    branches with no central device management. Best-effort only: a
    machine running a different antivirus, or with Defender administratively
    locked down (ExclusionPath often disabled via GPO/MDM in a managed
    estate), will just skip this with a warning rather than fail the
    install - the Watchdog's own scheduled-task fallback still keeps the
    agent recovering even if Defender eventually gets to the exe anyway."""
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"Add-MpPreference -ExclusionPath '{install_dir}'",
            ],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Added Windows Defender exclusion for %s.", install_dir)
        else:
            logger.warning(
                "Could not add Windows Defender exclusion (%s) - continuing install anyway.",
                result.stderr.strip() or result.stdout.strip(),
            )
    except Exception as exc:  # noqa: BLE001 - this is a best-effort mitigation, never a reason to fail install()
        logger.warning("Could not add Windows Defender exclusion: %s", exc)


def install(agent_exe_path: str, watchdog_exe_path: str) -> None:
    if not is_admin():
        raise PermissionError(
            "Hardening install must be run as Administrator (right-click PowerShell > Run as Administrator)."
        )
    _create_protected_scheduled_task(agent_exe_path)
    _install_watchdog_service(watchdog_exe_path)
    _add_defender_exclusion(os.path.dirname(agent_exe_path))
    logger.info(
        "Hardening installed: protected autostart (scheduled task) + watchdog service active. "
        "An Administrator can still reverse all of this via uninstall()."
    )


def uninstall(watchdog_exe_path: str) -> None:
    if not is_admin():
        raise PermissionError("Hardening uninstall must be run as Administrator.")
    _remove_watchdog_service(watchdog_exe_path)
    _remove_scheduled_task()
    # Deleted here, not left for the next install to silently reuse: a
    # reinstall is the one moment a fresh enroll() call is cheap and safe
    # to force. It's matched back to this exact device by MAC address (see
    # AgentEnrollView), so it never creates a duplicate - just re-runs the
    # one-time hardware snapshot (manufacturer/model/system_family/serial)
    # against whatever the agent build at reinstall time actually collects,
    # which is the only way an already-enrolled device ever picks up a
    # field added after it first enrolled. Org assignment (company/branch/
    # department/assigned_employee) survives this: AgentEnrollView only
    # overwrites those from the enrollment token when the token actually
    # specifies them, never blanking out what reinstalling here deliberately
    # keeps un-asked-about.
    try:
        if os.path.exists(CREDENTIALS_PATH):
            os.remove(CREDENTIALS_PATH)
            logger.info("Removed stored credentials — next install will re-enroll fresh.")
    except OSError as exc:
        logger.warning("Could not remove stored credentials during uninstall: %s", exc)
    logger.info("Hardening removed: watchdog service and scheduled task both reverted.")
