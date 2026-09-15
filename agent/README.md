# SentinelDesk Agent

Placeholder — implementasi dimulai di **Phase 2** (device registration, heartbeat)
sesuai roadmap. Struktur folder final:

```
agent/
├── src/
│   ├── main.py
│   ├── config/
│   ├── services/     # Windows Service wrapper (pywin32)
│   ├── monitoring/    # psutil collectors
│   ├── networking/    # WS/HTTPS client, reconnect/backoff
│   ├── enrollment/
│   └── screen/        # WebRTC capture (Phase 6)
├── requirements.txt
└── build/             # PyInstaller spec
```
