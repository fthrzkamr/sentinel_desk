# SentinelDesk Agent — MSI Installer

Packages the already-built agent + watchdog (see `../SentinelDeskAgent.spec`
and `../SentinelDeskWatchdog.spec`) into a real Windows `.msi`, so IT can
deploy to many laptops via GPO/Intune/RMM instead of copying the `.exe`
and running `--install-hardening` by hand on each one.

This installer doesn't reimplement any setup logic — it just calls the
agent's own CLI (`--install-hardening` / `--uninstall-hardening`, see
`../src/services/hardening.py`) as custom actions, the same commands an
admin would otherwise type from an elevated PowerShell.

## One-time setup

```powershell
dotnet tool install --global wix --version 5.0.2
wix extension add WixToolset.UI.wixext
```

(Version pinned to 5.0.2 - v7 introduced an Open Source Maintenance Fee
EULA requirement that 5.0.2 predates, so there's nothing extra to accept.)

## Build

```powershell
cd E:\sentinel_desk\agent
pyinstaller --clean --noconfirm SentinelDeskAgent.spec
pyinstaller --clean --noconfirm SentinelDeskWatchdog.spec
cd installer
.\build.ps1
```

Produces `installer\SentinelDeskAgent.msi`.

## Install

**Interactive** (double-click the `.msi`, or):
```powershell
msiexec /i SentinelDeskAgent.msi
```
Server URL defaults to `http://localhost:8000` and the enrollment token is
left blank — edit `C:\ProgramData\SentinelDesk\.env` afterward and
restart the agent (or just wait for the next scheduled-task logon trigger)
to finish enrollment.

**Silent, with real values** (per-device single-use token):
```powershell
msiexec /i SentinelDeskAgent.msi SERVERURL="http://your-server:8000" ENROLLMENTTOKEN="<token from the dashboard>" /qn
```
Enrollment happens automatically within seconds of install — no logon
required, no manual `.env` edit.

## Zero-touch mass deployment (reusable key + Pending Approval)

For pushing to many laptops (GPO/Intune/RMM) without generating one token
per device by hand:

1. On the dashboard's Agent Management page, create an enrollment token
   with the **"Reusable (deployment key)"** checkbox on. Unlike a normal
   token it isn't spent by the first device that uses it — copy its value
   once.
2. Bake it into the build itself:
   ```powershell
   .\build.ps1 -ServerUrl "http://your-server:8000" -EnrollmentToken "<reusable token>"
   ```
   The resulting `SentinelDeskAgent.msi` now installs and enrolls with
   **zero parameters** — a plain double-click or a silent
   `msiexec /i SentinelDeskAgent.msi /qn` both just work. The token is
   compiled into this one `.msi` file only, never written into
   `Product.wxs` (which stays in git with no secret in it).
3. Every device installed this way lands in the dashboard as **Pending
   Approval** (`is_approved = false`) — it's enrolled and credentialed,
   but every API call it makes 401s until an admin clicks **Approve** on
   the device (Devices list or Device Detail page). This is the mitigation
   for the reusable key being embedded in a file that could leak: on its
   own, the key can never produce a device that's actually reporting data
   without a human approving it first. A device enrolled through a normal,
   single-use token (step-1's checkbox left off) is unaffected and stays
   auto-approved immediately, exactly as before this feature existed.

## Monitoring defaults

Unlike a manually-configured device (everything opt-in/`false` by
default), an MSI install turns **every** monitor on by default (USB, App
Usage, Browsing History, File Activity, Idle Activity, System Errors, and
Live Screen) — a deliberate policy choice for centrally-deployed fleet
devices. This is written directly into the generated `.env`
(`build.ps1`), not a code-level default, so manually-configured devices
are unaffected.

The `.env` also gets an `INSTALLED_VIA_MSI=true` marker. The agent checks
for it at every startup (`config/settings.py`'s `_ensure_msi_defaults`)
and auto-appends `true` for any monitor flag it doesn't recognize yet in
that file — so if a future agent version adds a new monitor, an
already-installed MSI device picks up "on by default" for it automatically
the next time it restarts (e.g. after a self-update), with no reinstall or
manual `.env` edit needed. Manually-configured devices (no marker) are
untouched by this and keep falling back to `false` for anything not
explicitly set, same as always.

## What happens on install

1. Files copied to `C:\ProgramData\SentinelDesk\` (agent exe, watchdog
   folder, `.env`).
2. `icacls` grants `BUILTIN\Users` Modify on that folder (with
   inheritance), before anything else touches it. The agent runs as a
   standard, non-elevated user via the Scheduled Task — without this it
   can't create `logs\agent.log`, `credentials.dat`, or self-update its own
   exe, since a freshly-created ProgramData subfolder only grants standard
   users Read & Execute by default.
3. `.env` gets the real `SERVER_URL`/`ENROLLMENT_TOKEN` written in.
4. `SentinelDeskAgent.exe --install-hardening` runs elevated — sets up the
   protected Scheduled Task and starts the Watchdog Service (see
   `../src/services/hardening.py` for exactly what this does and
   doesn't do — it's opt-in tamper-resistance, not anything that stops an
   Administrator from managing the agent).
5. The scheduled task is triggered once immediately, so the agent starts
   (and enrolls, if a token was given) right away instead of waiting for
   the next logon.

## What happens on uninstall

Reverse order, via Settings → Apps or `msiexec /x SentinelDeskAgent.msi`:
`--uninstall-hardening` runs first (removes the Scheduled Task + Watchdog
Service) while the exe still exists on disk, then the process is
force-stopped, then all files — including `.env` and `credentials.dat` —
are removed. A reinstall re-enrolls as a new device.

## If `wix build` fails

Every custom action here uses the plain `ExeCommand` + `Directory` +
`Secure="yes"` property pattern documented by WiX for "run an installed
exe after files are in place" — the most standard, well-supported way to
do this, but it's untested against a real `wix build` as of when this was
written. If you hit a build or install-time error, the error message
itself (WiX's are usually specific about which line/attribute) is enough
to fix `Product.wxs` — it doesn't need re-deriving from scratch.
