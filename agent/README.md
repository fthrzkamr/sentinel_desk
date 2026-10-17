# SentinelDesk Agent

Windows endpoint agent: enrolls itself with the backend once (via a one-time
enrollment token), then reports hardware/OS metrics, software inventory, and
location on a schedule, and can stream its own screen live to an authorized
admin (only when explicitly enabled — see "Live screen" below).

## Running from source (development)

```bash
cd agent
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt

cp .env.example .env
# fill in ENROLLMENT_TOKEN (generate one from the admin dashboard's Agents page)

python src/main.py
```

Credentials issued at enrollment are stored encrypted (Windows DPAPI) in
`credentials.dat` next to `.env` — delete it to force re-enrollment.

### Environment variables (`.env`)

| Variable | Meaning |
|---|---|
| `SERVER_URL` | Backend base URL, e.g. `http://localhost:8000` |
| `ENROLLMENT_TOKEN` | One-time token from the admin dashboard — only needed for the very first run |
| `MONITOR_INTERVAL` | Seconds between metric samples (default 15) |
| `SCREEN_MONITOR_ENABLED` | `true`/`false` (default `false`) — kill-switch for live screen, see below |

## Live screen monitoring

Live screen is gated by **two independent controls**, not one:

1. Backend permission (`monitoring.live_screen`) + the admin explicitly
   starting a session from the dashboard — enforced server-side, can't be
   bypassed from the agent.
2. This agent's own `SCREEN_MONITOR_ENABLED` flag — off by default. Even if
   an admin has permission, this device won't respond to a live-screen
   request at all unless this is `true`.

Whenever a session is active, the monitored screen shows a persistent red
banner ("SentinelDesk: layar ini sedang dipantau oleh administrator") for as
long as it's being viewed — there is no silent/hidden mode.

## Building the .exe (PyInstaller)

```bash
cd agent
source venv/Scripts/activate
pip install -r requirements-build.txt
pyinstaller --clean --noconfirm SentinelDeskAgent.spec
```

Produces a single file at `dist/SentinelDeskAgent.exe` — no console window;
logs go to `dist/logs/agent.log`, `.env`/`credentials.dat` live next to the
exe (not wherever Windows happened to extract it to at runtime).

To actually deploy it to a machine: copy `SentinelDeskAgent.exe` and a
filled-in `.env` (with a real `ENROLLMENT_TOKEN`) into the same folder on
the target machine, then run the exe once.

### Auto-start at login

The exe registers itself in the current Windows user's
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` the first time it runs
successfully — no admin rights needed, and it re-registers on every launch
(so it stays correct if the exe is later moved). This only applies to the
packaged .exe, not `python src/main.py` from source.

To remove it: `SentinelDeskAgent.exe --uninstall-autostart`.

## Folder structure

```
agent/
├── src/
│   ├── main.py            # entry point — enrollment, metrics loop, shutdown
│   ├── config/             # .env loading, AgentConfig
│   ├── services/           # DPAPI credential storage, Windows auto-start
│   ├── monitoring/         # psutil metrics, software inventory, location
│   ├── networking/         # HTTP client to the backend, reconnect/backoff
│   └── screen/             # live-screen: capture, WebRTC, overlay, signaling
├── requirements.txt        # runtime dependencies (what the .exe ships with)
├── requirements-build.txt  # build-only tooling (PyInstaller)
└── SentinelDeskAgent.spec  # PyInstaller build spec
```
