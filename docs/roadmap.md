# SentinelDesk — Roadmap

| Phase | Fokus | Status |
|---|---|---|
| 1 | Project setup: Django, PostgreSQL, Vue, Docker, Authentication | ✅ Selesai |
| 2 | Device registration, Agent dasar, Heartbeat, Device dashboard | ✅ Selesai (backend, agent, UI Devices & Agent Management) |
| 3 | CPU/RAM/Disk/Battery monitoring, WebSocket realtime | ✅ Selesai (metrics ingest, threshold status, WS dashboard, Celery offline detection) |
| 4 | Hardware & software inventory | ✅ Selesai (hardware sudah dari Phase 2-3; software inventory baru: registry scan, sync, search/filter/sort/export) |
| 5 | Location monitoring, history, Map | ✅ Selesai (Windows Location Service + fallback IP geolocation, peta Leaflet, riwayat) |
| 6 | Live screen monitoring via WebRTC | ✅ Selesai (signaling relay per-device via Channels, RBAC + audit log wajib, satu viewer per device, overlay peringatan di layar device, kill-switch `SCREEN_MONITOR_ENABLED` di agent) |
| 7 | Alerts, Audit log lengkap, RBAC penuh | ✅ Selesai (alert engine per-metrik dengan auto-resolve, halaman Alerts + notification bell, REST audit log dengan filter/search + halaman Audit Logs, CRUD user + assign role via UI) |
| 8 | Security hardening, testing, deployment, packaging Agent .exe | ✅ Selesai (git init + CI, throttle & production settings hardening, docker-compose.prod.yml + nginx generik, Agent .exe via PyInstaller + auto-start) |

Prinsip: setiap phase harus stabil & teruji sebelum lanjut ke phase berikutnya.
Lihat percakapan awal proyek untuk arsitektur final, ERD, dan alur komunikasi
lengkap (enrollment, realtime monitoring, live screen).

---

## Pengembangan Lanjutan (Post-Phase 8)

Rincian lengkap saran pengembangan berikutnya beserta status pengerjaan per-item dapat dilihat di [`docs/pengembangan-lanjutan.md`](./pengembangan-lanjutan.md):

| Tahap | Fokus Pengembangan | Status |
|---|---|---|
| **Tahap 1** | **Quick Wins & Stabilitas Inti** (Cache `SystemSettings`, Celery di `docker-compose.prod.yml`, Broadcast WebSocket semua kategori Alert, Ketahanan Sync Agent) | ✅ Selesai |
| **Tahap 2** | **Notifikasi Eksternal & Eskalasi Insiden** (Telegram / Webhook / Email via Celery) | ✅ Selesai |
| **Tahap 3** | **Export Laporan (CSV) & Optimasi Ringkasan Dashboard** | ✅ Selesai |
| **Tahap 4** | **Manajemen Agent Jarak Jauh** (HTTP Session Pooling, Remote Config Policy, OTA Auto-Update) | ✅ Selesai |
| **Tahap 5** | **Peningkatan Live Screen WebRTC** (TURN Server & Multi-Monitor Selector) | ✅ Selesai |
| **Tahap 6** | **Keamanan Lanjutan & CI/CD Agent** (2FA/TOTP Admin, Retensi Alert, CI Test Agent) | ✅ Selesai |
| **Tahap 7** | **Remote Control & Remote Assistance** (WebRTC DataChannel, Windows SendInput, Toolbar Pintasan & Clipboard) | ✅ Selesai |
