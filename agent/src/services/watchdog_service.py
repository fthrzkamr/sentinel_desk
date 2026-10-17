"""A minimal Windows Service whose only job is to keep the SentinelDesk
agent process running. Installed once by an admin (see `hardening.py`) as
its own separate .exe (SentinelDeskWatchdog.exe) — a Windows service is not
something a standard/non-admin employee can stop from Task Manager, and
Windows itself restarts it on crash, so it is a much sturdier anchor than
the agent process it's watching over.

It never starts the agent directly: a SYSTEM-context service can't launch
a GUI/desktop process into a logged-on user's session without duplicating
that user's security token, which is exactly what the Task Scheduler
already does correctly for a "run only when user is logged on" task. So
the service's recovery action is simply to re-trigger that scheduled task.

This intentionally does NOT try to hide the agent process, make it
unkillable even by an Administrator, or interfere with antivirus — see
hardening.py's module docstring for why."""

import logging
import os
import subprocess
import sys

# A real Windows service has no console at all, so sys.stdout/sys.stderr are
# None (or a broken stream) here — unlike running this same exe interactively
# ("SentinelDeskWatchdog.exe debug"), where a console is attached and hides
# the problem. If anything anywhere (this file, or inside pywin32 itself)
# ever calls print()/writes a warning, that raises immediately and kills the
# process before Windows' Service Control Manager gets an ack, with nothing
# useful logged anywhere to explain why. Point both at a real file before
# importing pywin32, so nothing can crash on a write with no destination.
if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
    _stub_dir = os.path.dirname(sys.executable)
    _stub_path = os.path.join(_stub_dir, "logs")
    os.makedirs(_stub_path, exist_ok=True)
    _stub = open(os.path.join(_stub_path, "watchdog_stdio.log"), "a", buffering=1)
    sys.stdout = _stub
    sys.stderr = _stub

import win32event
import win32service
import win32serviceutil


def _log_dir() -> str:
    # Deliberately self-contained rather than importing config.settings —
    # this service has no agent config to load, and pulling that module in
    # would mean a failure loading .env could take the whole service down
    # with it before it even gets a chance to log anything.
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(base, "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


# servicemanager.LogMsg/LogInfoMsg write to the Windows Event Log, which
# needs the service's event source properly registered — running as a real
# SYSTEM-context service (as opposed to `SentinelDeskWatchdog.exe debug`,
# which prints to the console instead), that registration silently failing
# was enough to crash the service before it logged anything at all, with
# nothing in Event Viewer to explain why. A plain text log file next to the
# exe has no such registration step, so it can't fail the same way.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(os.path.join(_log_dir(), "watchdog.log"), encoding="utf-8")],
)
logger = logging.getLogger("sentineldesk.watchdog")

AGENT_PROCESS_NAME = "SentinelDeskAgent.exe"
SCHEDULED_TASK_NAME = "SentinelDeskAgent"
CHECK_INTERVAL_SECONDS = 30


def _is_agent_running() -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {AGENT_PROCESS_NAME}"],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return AGENT_PROCESS_NAME.lower() in result.stdout.lower()


def _relaunch_agent() -> None:
    subprocess.run(
        ["schtasks", "/Run", "/TN", SCHEDULED_TASK_NAME],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _kill_agent() -> None:
    subprocess.run(
        ["taskkill", "/F", "/IM", AGENT_PROCESS_NAME],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _agent_stuck_on_dialog() -> bool:
    """`_is_agent_running()`'s tasklist check only proves a process named
    SentinelDeskAgent.exe exists - it can't tell "running normally" apart
    from "alive but frozen on a blocking native dialog" (confirmed live:
    the PyInstaller onefile bootloader's own "Failed to load Python DLL"
    MessageBox, which showed up during ordinary antivirus-vs-onefile-
    extraction races and then sat on an unattended laptop's screen for ten
    minutes with nobody to click OK). The agent has no UI at all in normal
    operation (console=False, no windows) - so ANY visible window title
    means stuck, never "merely busy"."""
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command",
                "(Get-Process -Name '" + os.path.splitext(AGENT_PROCESS_NAME)[0] + "' -ErrorAction SilentlyContinue "
                "| Where-Object { $_.MainWindowTitle }).Count",
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.stdout.strip() not in ("", "0")


class SentinelDeskWatchdogService(win32serviceutil.ServiceFramework):
    _svc_name_ = "SentinelDeskWatchdog"
    _svc_display_name_ = "SentinelDesk Watchdog"
    _svc_description_ = (
        "Restarts the SentinelDesk endpoint agent if it stops running. "
        "Stopping or removing this service requires Administrator rights."
    )

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = True

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        self.running = False

    def SvcDoRun(self):
        logger.info("SentinelDeskWatchdog service started.")
        self.main()

    def main(self):
        while self.running:
            try:
                if _is_agent_running() and _agent_stuck_on_dialog():
                    logger.info("SentinelDesk agent is stuck on a blocking dialog — killing and relaunching.")
                    _kill_agent()
                    _relaunch_agent()
                elif not _is_agent_running():
                    logger.info("SentinelDesk agent not running — relaunching via scheduled task.")
                    _relaunch_agent()
            except Exception as exc:  # noqa: BLE001 — a watchdog must never die from a transient check failure
                logger.error("Watchdog check failed (will retry next interval): %s", exc)
            rc = win32event.WaitForSingleObject(self.stop_event, CHECK_INTERVAL_SECONDS * 1000)
            if rc == win32event.WAIT_OBJECT_0:
                break


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # This is exactly how Windows' Service Control Manager launches a
        # real service — no arguments at all. HandleCommandLine is supposed
        # to detect that and dispatch straight to the SCM itself, but that
        # detection doesn't reliably work once pywin32 is frozen by
        # PyInstaller (a well-documented pywin32 + PyInstaller gap) — it was
        # instead printing a CLI usage message and exiting immediately,
        # which is why the service kept reporting STOPPED with no actual
        # crash anywhere to explain it. Driving the same three calls
        # manually here is the standard workaround.
        import servicemanager

        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SentinelDeskWatchdogService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SentinelDeskWatchdogService)
