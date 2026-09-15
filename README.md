# SentinelDesk

IT Endpoint Monitoring & Device Management — Admin Web Dashboard, Backend API,
dan Client Agent untuk perangkat Windows yang terdaftar dan diotorisasi.

Status saat ini: **Phase 1-8 (semua phase) selesai dan teruji** — setup &
auth, device registration & agent, realtime monitoring via WebSocket,
software inventory, location monitoring, live screen via WebRTC, alerts,
audit log, RBAC penuh, security hardening, CI, production deployment stack,
dan Agent yang sudah bisa dikemas jadi `.exe`. Lihat `docs/roadmap.md` untuk
rincian tiap phase.

## Struktur Proyek

```
sentineldesk/
├── backend/     # Django + DRF + Channels (Docker)
├── frontend/    # Vue 3 + Vite + Pinia + Tailwind (Docker)
├── agent/       # SentinelDesk Agent (Windows) — jalan native, lihat bagian 5
├── nginx/       # Reverse proxy — mulai Phase 8 (production)
├── docker-compose.yml   # Postgres + Redis + backend + frontend
├── .env.example
└── docs/
```

## Prasyarat

- Docker Desktop
- Python 3.11+ (hanya untuk menjalankan **Agent**, lihat bagian 5 — backend
  jalan di dalam container, tidak butuh Python di host)
- Node.js (opsional — hanya kalau mau menjalankan tooling frontend di luar
  container; dev server sehari-hari sudah otomatis lewat Docker)

## 1. Environment Variables

```bash
cp .env.example .env
```

Satu file `.env` di root ini di-inject langsung ke container `backend` dan
`frontend` lewat `env_file:` di `docker-compose.yml`. Isi variabel penting:

| Variable | Keterangan |
|---|---|
| `DJANGO_SECRET_KEY` | Wajib diisi nilai acak, jangan dipakai bersama di lingkungan lain |
| `DATABASE_URL` | Dipakai backend **di dalam container** → host-nya `postgres` (nama service Docker), bukan `localhost` |
| `REDIS_URL` | Sama, host-nya `redis` (nama service Docker) |
| `POSTGRES_PORT` | Port yang dibuka ke host (mis. buat GUI DB client) — default `5433`, sengaja dihindari dari `5432` karena sering bentrok dengan PostgreSQL lokal yang sudah terpasang |
| `CORS_ALLOWED_ORIGINS` | Origin frontend yang diizinkan mengakses API — tetap `http://localhost:5173` karena ini dibaca browser, bukan dari dalam Docker network |
| `VITE_API_BASE_URL` / `VITE_WS_BASE_URL` | Dibaca frontend (browser) untuk memanggil backend — tetap `localhost:8000` dengan alasan yang sama |

## 2. Jalankan semuanya

```bash
docker compose up -d --build
docker compose ps   # pastikan semua "Up" / "healthy"
```

Ini menyalakan 4 service sekaligus: `postgres`, `redis`, `backend` (Django,
otomatis `migrate` lalu `runserver` di port 8000), `frontend` (Vite dev
server di port 5173). Kode di `backend/` dan `frontend/` di-mount sebagai
volume, jadi **hot-reload tetap jalan** persis seperti dev native — ubah
file di editor, browser/server otomatis reload tanpa perlu rebuild image.
Rebuild image (`--build`) hanya perlu kalau `requirements/*.txt` atau
`package.json` berubah.

Command satu-kali (migrate ulang, seed data, dll) dijalankan lewat
`docker compose exec`:

```bash
docker compose exec backend python manage.py seed_rbac        # 4 role default + 11 permission
docker compose exec backend python manage.py createsuperuser  # akun admin pertama
docker compose exec backend pytest                              # test suite
```

Lihat log tiap service dengan `docker compose logs -f backend` (atau
`frontend`). Backend berjalan di `http://localhost:8000`, frontend di
`http://localhost:5173`.

### RBAC yang sudah di-seed

| Role | Cakupan |
|---|---|
| `SUPER_ADMIN` | Semua permission, termasuk `user.manage` |
| `IT_ADMIN` | Semua permission operasional, tanpa `user.manage` |
| `IT_OPERATOR` | Monitoring, live screen, alert, tanpa manage device/agent |
| `VIEWER` | Read-only (`*.view`) |

Assign role ke user lewat Django admin (`/admin/`) pada field `role`.

## 3. Frontend (referensi — sudah otomatis jalan lewat Docker compose)

Bagian ini hanya relevan kalau butuh menjalankan tooling frontend (mis.
`npm run build` untuk produksi) di luar container:

```bash
cd frontend
npm install
npm run dev
```

Frontend berjalan di `http://localhost:5173`, sudah terhubung ke backend lewat
`src/services/api.js` (axios + auto-refresh token JWT) dan `src/stores/auth.js`
(Pinia).

## 4. SentinelDesk Agent

Agent saat ini adalah skrip Python yang dijalankan manual — pembungkusan
sebagai Windows Service dan `.exe` (PyInstaller) baru masuk di Phase 8.

```bash
cd agent
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt

cp .env.example .env
# isi ENROLLMENT_TOKEN dengan token dari admin (lihat langkah di bawah)

python src/main.py
```

Cara mendapatkan `ENROLLMENT_TOKEN` (perlu permission `agent.manage`, contoh
pakai akun `admin`):

```bash
ACCESS=$(curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<password>"}' | python -c "import sys,json;print(json.load(sys.stdin)['access'])")

curl -X POST http://localhost:8000/api/agent/enrollment-tokens/ \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{"label":"laptop-budi"}'
```

Token hanya ditampilkan sekali di response `token`, berlaku
`ENROLLMENT_TOKEN_TTL_MINUTES` menit (default 60), dan sekali pakai. Setelah
enroll sukses, `device_token` hasil enroll disimpan terenkripsi (Windows
DPAPI) di `agent/credentials.dat` — bukan plaintext — dan dipakai lagi di run
berikutnya tanpa perlu enroll ulang.

## 5. Realtime pipeline (Celery worker + beat) — opsional untuk dev

Metrics (CPU/RAM/Disk/Battery) dan update status device WARNING/CRITICAL
sudah realtime lewat WebSocket tanpa perlu Celery — itu terjadi langsung saat
`POST /api/agent/metrics/` diproses. Celery **hanya** dibutuhkan untuk dua
pekerjaan periodik:

- Menandai device **OFFLINE** ketika sudah tidak mengirim data melebihi
  `DEVICE_OFFLINE_THRESHOLD_SECONDS` (setiap 20 detik).
- Membersihkan `DeviceMetric` yang lebih tua dari `DEVICE_METRIC_RETENTION_DAYS`
  (setiap 1 jam).

Belum ada service `celery`/`celery-beat` permanen di `docker-compose.yml` —
untuk mencobanya saat dev, jalankan di dalam container `backend` yang sudah
ada (dua proses terpisah):

```bash
docker compose exec backend celery -A config worker -l info
docker compose exec backend celery -A config beat -l info
```

Tanpa proses ini, device yang agent-nya dimatikan akan tetap tampil status
terakhirnya (mis. ONLINE) sampai worker+beat berjalan dan menandainya OFFLINE.

## 6. Deployment (production)

`docker-compose.prod.yml` adalah stack production generik — belum di-deploy
ke server sungguhan mana pun (belum ada domain/server tujuan), tapi sudah
diuji jalan penuh di komputer ini. Bedanya dari dev:

- Backend jalan dari `backend/Dockerfile.prod` (`requirements/prod.txt`
  saja, Daphne bukan `runserver`, kode di-`COPY` sekali ke image — bukan
  bind-mount, jadi tidak hot-reload, harus rebuild tiap ada perubahan kode).
- Frontend di-build jadi static file (`npm run build`) lalu di-serve nginx
  (`frontend/Dockerfile.prod`), bukan Vite dev server.
- Satu `nginx` di depan semuanya (`nginx/conf.d/default.conf`) — port 80
  saja yang dibuka ke host; postgres/redis/backend/frontend tidak bisa
  diakses langsung dari luar.

```bash
cp .env.prod.example .env.prod
# isi DJANGO_SECRET_KEY, POSTGRES_PASSWORD, domain asli, dst.

docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

`--env-file .env.prod` **wajib** — tanpa itu, `${POSTGRES_DB}` dkk. di
`docker-compose.prod.yml` tidak ke-resolve dan postgres gagal start (ini
mekanisme substitusi variabel compose sendiri, terpisah dari `env_file:`
yang meng-inject env ke dalam container).

TLS belum dikonfigurasi (`nginx/conf.d/default.conf` baru dengar di port 80
plain HTTP) karena belum ada domain/sertifikat sungguhan — begitu ada,
tambahkan server block 443 di file itu dengan sertifikatnya, lalu set
`DJANGO_HTTPS_ENABLED=true` di `.env.prod` supaya Django ikut mengaktifkan
`SECURE_SSL_REDIRECT`/HSTS/cookie secure (lihat komentar di
`config/settings/production.py` — mengaktifkannya sebelum TLS benar-benar
ada di nginx malah bikin redirect loop, bukan lebih aman).

## Apa yang sudah berfungsi di Phase 1

- Custom `User`, `Role`, `Permission` model — RBAC granular, dicek di backend
  (lihat `apps/accounts/permissions.py`), bukan hanya disembunyikan di UI.
- Login JWT (`/api/auth/login/`), refresh (`/api/auth/refresh/`), logout dengan
  token blacklist (`/api/auth/logout/`), current-user (`/api/auth/me/`).
- Audit log otomatis untuk `auth.login`, `auth.login_failed`, `auth.logout`
  (`apps/audit`), read-only di Django admin.
- Rate limiting login (`10/min`) via DRF throttling.
- CORS, security headers dasar, `.env`-based config — tidak ada secret
  hardcode.
- ASGI + Channels sudah terpasang (routing kosong, siap dipakai Phase 3).
- Vue Router dengan auth guard, Pinia store, Tailwind, sidebar navigasi sesuai
  seluruh halaman yang direncanakan (menu Phase berikutnya ditandai "Soon").
- 6 app Django lain (`devices`, `monitoring`, `locations`, `software`,
  `alerts`) sudah discaffold sebagai app kosong, siap diisi model di Phase 2+.

## Apa yang sudah berfungsi di Phase 2 (backend + agent + UI)

- Model `Device`, `DeviceCredential`, `EnrollmentToken`, `Company`, `Branch`,
  `Department`, `Employee` (`apps/devices`).
- Enrollment token: sekali pakai, ada expiry, bisa direvoke, hanya prefix-nya
  yang disimpan bisa dibaca kembali (`token_prefix`) — token asli hanya
  ditampilkan sekali saat dibuat.
- Alur enrollment penuh: `POST /api/agent/enroll/` (public + token) →
  membuat `Device` dengan ID `SD-LPT-000001`, dst. → mengembalikan
  `device_token` sekali → device disimpan lewat `DeviceCredential` (di-hash,
  bukan plaintext).
- Autentikasi khusus agent (`apps/devices/authentication.py`): header
  `X-Device-ID` + `Authorization: DeviceToken <token>` — terpisah total dari
  JWT admin.
- `POST /api/agent/heartbeat/` — update `last_seen` & status `ONLINE`,
  ditolak (401) jika device `DISABLED` atau token salah.
- `GET /api/devices/`, `GET /api/devices/{device_id}/`,
  `POST /api/devices/{device_id}/disable/` |`/enable/` — semua dicek
  permission `device.view` / `device.disable` di backend.
- Audit log otomatis: `device.registered`, `device.disabled`,
  `device.enabled`, `agent.enrollment_token_created`,
  `agent.enrollment_token_revoked`, `agent.enroll_failed`.
- Agent Python (`agent/src/`): enrollment sekali jalan, heartbeat berkala
  (`MONITOR_INTERVAL`), auto-reconnect dengan exponential backoff, kredensial
  tersimpan terenkripsi DPAPI di `credentials.dat`.
- Diuji dengan agent sungguhan (bukan cuma curl): enroll → 2x heartbeat →
  restart agent → kredensial dipakai ulang tanpa enroll ulang.
- 8 pytest baru untuk devices app (enroll, single-use token, token expired,
  heartbeat, device disabled ditolak, RBAC per-role) — total 14 test (6 dari
  Phase 1 + 8 baru), semua passed.
- **Halaman Devices** (`/devices`): tabel dengan search + filter status,
  badge status berwarna, tombol Disable/Enable (muncul hanya untuk role yang
  punya permission `device.disable`), pagination.
- **Device Detail** (`/devices/:deviceId`): tab Overview & Hardware berisi
  data asli device (field yang belum tersedia ditampilkan "Not Available",
  bukan data palsu), tab lain (Software, Location, Live Screen, History,
  Audit) ditandai jelas "tersedia di phase berikutnya". Tombol Disable/Enable
  dengan dialog konfirmasi.
- **Agent Management** (`/agents`): generate enrollment token (label + masa
  berlaku), token asli hanya ditampilkan sekali dengan tombol copy, daftar
  token dengan status Valid/Used/Expired/Revoked, tombol Revoke.
- Sidebar & routing menghormati permission asli dari backend
  (`auth.hasPermission()`) — menu disembunyikan dan route diblokir kalau user
  tidak punya izin, tapi ini hanya UX; backend tetap sumber kebenaran.
- Diuji end-to-end lewat browser sungguhan (bukan cuma curl): buat token di
  UI → jalankan agent asli → device muncul ONLINE di tabel → buka detail →
  disable lewat dialog konfirmasi → badge & tombol berubah sesuai.

## Apa yang sudah berfungsi di Phase 3 (realtime monitoring)

- Model `DeviceMetric` (`apps/monitoring`) — CPU%, frekuensi CPU, RAM
  (total/used/%), Disk (total/used/free/%), network upload/download (kbps),
  battery (%, charging), uptime.
- `POST /api/agent/metrics/` — agent kirim sample setiap `MONITOR_INTERVAL`
  detik; endpoint ini yang sekarang dipakai agent (menggantikan panggilan
  heartbeat terpisah), sekaligus mengevaluasi status device:
  **CRITICAL** (CPU/RAM/Disk sangat tinggi, atau baterai kritis & tidak
  charging) > **WARNING** (salah satu di atas ambang) > **ONLINE**. Threshold
  bisa diatur lewat env var (`CPU_WARNING_PERCENT`, dst. — lihat
  `.env.example`).
- `GET /api/devices/{device_id}/metrics/` (sample terakhir) dan
  `.../history/` (riwayat, paginated).
- **WebSocket** `ws://localhost:8000/ws/dashboard/?token=<access_token>`
  (`apps/monitoring/consumers.py`) — push realtime ke browser admin setiap
  ada metric baru atau device berubah status, dengan autentikasi JWT di query
  string (bukan cookie session) dan permission `monitoring.view`. Koneksi
  tanpa token atau token tidak valid langsung ditolak.
- Celery task `mark_stale_devices_offline` (setiap 20 detik) — device yang
  berhenti kirim data lebih dari `DEVICE_OFFLINE_THRESHOLD_SECONDS` otomatis
  jadi OFFLINE dan di-broadcast ke dashboard. `prune_old_metrics` membuang
  data mentah lebih tua dari `DEVICE_METRIC_RETENTION_DAYS` (default 7 hari).
- **Dashboard** (`/`): stat card Total/Online/Offline/Warning/Critical +
  rata-rata CPU/RAM sekarang berisi angka asli (bukan placeholder), dan
  tabel "Device Paling Baru Aktif" — semuanya update otomatis lewat
  WebSocket tanpa refresh.
- **Devices list**: kolom CPU/RAM/Disk menampilkan persentase pemakaian
  realtime (fallback ke spec hardware statis kalau belum ada data), badge
  status ikut live update.
- **Device Detail → tab Metrics**: progress bar CPU/RAM/Disk berwarna
  (hijau/kuning/merah sesuai threshold), battery, network, uptime — nilai
  live dari WebSocket, fallback ke REST `GET .../metrics/` saat halaman
  pertama dibuka.
- Diuji end-to-end dengan agent sungguhan: WebSocket menerima broadcast
  persis saat agent mengirim metric, termasuk transisi status
  ONLINE → WARNING → CRITICAL sesuai nilai CPU asli, dan broadcast
  lintas-proses (simulasi Celery) diverifikasi lewat Redis channel layer.
- 14 pytest baru untuk monitoring app (ingest, threshold, permission,
  WebSocket auth + broadcast pakai `channels.testing.WebsocketCommunicator`)
  — total 28 test, semua passed.

## Apa yang sudah berfungsi di Phase 4 (software inventory)

Hardware sebagian besar sudah tercakup dari Phase 2 (spec CPU/RAM/Disk saat
enrollment) & Phase 3 (pemakaian realtime + threshold), jadi fokus Phase 4
ada di **software inventory**:

- Model `Software` (`apps/software`) — satu baris per software per device.
  Setiap agent sync, baris lama device itu **dihapus & diganti total** dengan
  daftar terbaru (bukan menumpuk histori) — jadi selalu mencerminkan software
  yang benar-benar terpasang saat ini, otomatis "hilang" dari daftar kalau
  di-uninstall.
- Agent (`agent/src/monitoring/software_inventory.py`) — baca daftar program
  terinstall lewat registry Windows (`...CurrentVersion\Uninstall`, mesin
  yang sama dipakai "Programs and Features" bawaan Windows) — **tidak**
  membaca file pribadi user. Entry system component & update/patch
  disaring biar tidak berisik.
- `POST /api/agent/software/` — agent kirim sekali saat startup, lalu
  berkala tiap 1 jam (bukan tiap siklus metrics yang cepat, karena daftar
  software jarang berubah).
- `GET /api/software/` — permission `software.view`, mendukung **search**
  (nama/publisher), **filter** per device (`?device=SD-LPT-000001`), dan
  **sort** (`?ordering=name` / `-name`, dst.) sesuai spesifikasi awal.
- **Halaman Software Inventory** (`/software`, menu sidebar) — tabel global
  semua device dengan search, filter Device ID, kolom bisa diklik buat sort,
  dan tombol **Export CSV** (murni di browser, tanpa endpoint backend
  tambahan).
- **Device Detail → tab Software** — versi terfilter untuk device itu saja,
  search + export CSV sendiri, di-load malas (baru fetch pas tab-nya
  diklik pertama kali).
- Diuji dengan agent sungguhan di komputer ini sendiri: 55 software asli
  terdeteksi (7-Zip, Docker Desktop, driver printer, dll.) dan tampil benar
  di kedua halaman, search & sort dicoba langsung di browser.
- Ketemu 1 bug nyata di test suite (bukan di aplikasi): cache rate-limit
  login tidak ke-reset antar test, bikin test gagal kalau suite penuh
  dijalankan berurutan — sudah diperbaiki lewat `backend/conftest.py`
  (`cache.clear()` otomatis tiap test).
- 5 pytest baru untuk software app (sync, replace-on-resync, permission,
  search+filter, sort) — total 33 test, semua passed.

## Apa yang sudah berfungsi di Phase 5 (location monitoring)

- Model `Location` (`apps/locations`) — latitude/longitude/accuracy semuanya
  **nullable**: kalau sumbernya tidak bisa menentukan posisi, sistem
  mencatat percobaannya (source + timestamp) tanpa mengarang koordinat.
- Agent (`agent/src/monitoring/location.py`) — minta lokasi ke **Windows
  Location Service** (`winsdk`, WinRT API resmi Windows). Agent tidak pernah
  bicara langsung ke chip GPS; Windows sendiri yang memutuskan pakai
  GPS/Wi-Fi-positioning/apa pun sesuai hardware & izin privasi yang aktif di
  sistem. Sinkron sekali saat startup, lalu tiap 15 menit.
- Kalau OS location tidak tersedia/ditolak, **backend** (bukan agent) yang
  mengestimasi dari alamat IP request (`apps/locations/services.py`, lookup
  ke `ip-api.com`, khusus dilakukan di server karena backend sudah tahu IP
  device tanpa agent perlu request keluar sendiri). IP privat/lokal (mis.
  `192.168.x`, `127.0.0.1`) otomatis dikenali tidak bisa diestimasi —
  bukan dipaksakan jadi angka. Akurasi IP geolocation diberi label jelas
  ±5 km (level kota), **tidak pernah** diklaim presisi.
- `POST /api/agent/location/`, `GET /api/locations/` (lokasi terakhir tiap
  device, buat overview peta), `GET /api/devices/{device_id}/locations/`
  (riwayat), semua permission `location.view`.
- **Halaman Map** (`/map`) — peta interaktif (Leaflet + OpenStreetMap, gratis
  tanpa API key) menampilkan semua device dengan lokasi diketahui, lingkaran
  radius akurasi di sekitar tiap marker, dan daftar terpisah untuk device
  yang lokasinya tidak diketahui (supaya jelas bukan disembunyikan/error).
- **Device Detail → tab Location** — peta device tersebut + riwayat lokasi
  (waktu, sumber, koordinat, akurasi), lazy-load saat tab dibuka.
- Diuji dengan agent sungguhan di komputer ini: **Windows Location Service
  ternyata aktif** di mesin ini dan mengembalikan koordinat asli (Jakarta
  Barat, akurasi ±83 m) — muncul benar di peta maupun tab Location. Jalur
  fallback IP-geolocation juga diuji manual lewat curl (IP lokal → hasil
  `null` yang jujur, bukan koordinat palsu).
- 11 pytest baru untuk locations app (unit test estimasi IP dengan mock
  network call, ingest OS vs fallback IP, validasi lat/lng harus sepasang,
  permission, latest-per-device, riwayat) — total 44 test, semua passed.

## Apa yang sudah berfungsi di Phase 6 (live screen monitoring via WebRTC)

Fitur paling sensitif di spec — dibatasi ketat sesuai constraint keamanan:
hanya bisa dipakai kalau device sudah terdaftar **dan** admin punya permission
`monitoring.live_screen`, satu device hanya boleh dilihat satu admin dalam
satu waktu, setiap mulai/berhenti/gagal sesi tercatat di audit log, dan
device yang sedang dipantau **selalu** menampilkan banner peringatan di
layarnya sendiri — tidak ada mode diam-diam.

- **Signaling** (`apps/livescreen`) — dua WebSocket consumer terpisah lewat
  Django Channels: `ws/agent/{device_id}/signal/` (autentikasi device token)
  dan `ws/livescreen/{device_id}/` (autentikasi JWT admin + cek permission).
  Keduanya di-relay point-to-point lewat `channel_layer.send()` langsung ke
  channel name lawan bicara (bukan Channels group) — supaya pesan admin A
  tidak pernah bisa nyasar ke admin B yang kebetulan buka device lain.
- **Presence** (`apps/livescreen/presence.py`) — status "agent online" dan
  "sedang dilihat siapa" disimpan di Redis cache dengan TTL 60 detik; agent
  wajib kirim ping app-level tiap 20 detik supaya tidak dianggap offline.
- Video/audio **tidak pernah lewat server** — backend hanya menyambungkan
  SDP offer/answer (signaling), lalu koneksi WebRTC-nya peer-to-peer langsung
  antara browser admin dan agent (STUN publik Google untuk NAT traversal,
  tanpa TURN/relay media).
- Agent (`agent/src/screen/`) — `capture_track.py` (capture layar lewat
  `mss`, dibatasi resolusi maks. 1280px lebar & 12 fps supaya hemat bandwidth
  dan CPU, **bukan** full-res/full-fps), `webrtc_session.py` (`aiortc`,
  browser admin selalu jadi pihak yang membuat offer), `overlay.py` (banner
  merah always-on-top pakai Tkinter, jalan di thread terpisah, muncul
  otomatis selama streaming aktif dan hilang otomatis saat berhenti),
  `signaling_client.py` (koneksi persisten ke backend, reconnect+backoff,
  jalan di thread & event loop `asyncio` sendiri supaya tidak mengganggu
  loop metrics yang sudah berjalan).
- Live screen di agent **mati secara default** — hanya aktif kalau
  `SCREEN_MONITOR_ENABLED=true` di `.env` agent, sebagai kill-switch teknis
  tambahan di luar permission backend.
- Tidak ada fitur perekaman/penyimpanan (screen recording, screenshot
  otomatis, keylogger, capture password/cookie/token) — sesuai batasan keras
  di spec awal proyek.
- **Device Detail → tab Live Screen** — tombol Mulai/Hentikan, indikator
  status (Tidak aktif / Menghubungkan / Streaming aktif / Error), video
  langsung dari `RTCPeerConnection` browser (bukan lewat server), tab hanya
  muncul aktif untuk user yang punya permission `monitoring.live_screen`
  (dicek ulang di backend, bukan cuma disembunyikan di UI). Pindah tab atau
  keluar halaman otomatis menghentikan sesi & koneksi WebRTC.
- Diuji end-to-end dengan agent sungguhan di komputer ini + browser asli
  (Playwright): device di-enroll, login sebagai admin, klik "Mulai Live
  Screen" di tab Live Screen — layar asli komputer ini (1280x720) tampil di
  dashboard lengkap dengan banner peringatan di capture-nya, video state
  `readyState=4` (bisa diputar), lalu "Hentikan" menutup `RTCPeerConnection`
  dengan bersih di kedua sisi tanpa mengganggu loop metrics agent yang tetap
  jalan. Audit log `livescreen.started` / `livescreen.stopped` /
  `livescreen.start_failed` (agent offline, atau device sudah dilihat admin
  lain) terverifikasi tercatat dengan user & alasan yang benar.
- 5 pytest baru untuk livescreen app (token invalid, permission, agent
  offline, relay dua arah + audit log, viewer kedua ditolak pakai
  `channels.testing.WebsocketCommunicator`) — total 49 test, semua passed.

## Apa yang sudah berfungsi di Phase 7 (alerts, audit log, RBAC penuh)

- **Alert engine** (`apps/alerts`) — satu baris `Alert` per kondisi yang
  sedang berlangsung (bukan satu baris per metric sample): dibuat sekali saat
  CPU/RAM/Disk melewati `*_WARNING_PERCENT`/`*_CRITICAL_PERCENT` (threshold
  yang sama persis dengan status device di Phase 3) atau baterai kritis saat
  tidak charging, **auto-resolve** begitu metrik berikutnya kembali normal —
  tidak menumpuk alert duplikat selama kondisinya tetap sama. Device yang
  offline (dideteksi oleh task Celery yang sudah ada) juga memicu alert
  `CONNECTIVITY`, otomatis resolve saat device kirim metric lagi.
- `GET /api/alerts/` (filter status/severity/category + by device),
  `GET /api/alerts/summary/` (hitungan open/critical untuk badge notifikasi),
  `POST /api/alerts/{id}/acknowledge/` & `.../resolve/` — permission
  `alert.view` / `alert.manage`, setiap acknowledge/resolve tercatat di audit
  log dan di-broadcast realtime ke dashboard (channel WebSocket yang sama
  dari Phase 3, event baru `alert.triggered` / `alert.updated`).
- **Halaman Alerts** (`/alerts`) — tabel dengan filter status/severity/
  kategori, tombol Acknowledge/Resolve (muncul sesuai permission), badge
  warna per severity/status.
- **Bell notifikasi** di topbar (semua halaman) — jumlah alert open realtime
  via WebSocket, merah kalau ada yang critical, klik langsung ke halaman
  Alerts.
- **Audit log REST API** (`apps/audit`, sebelumnya hanya bisa dilihat lewat
  Django admin) — `GET /api/audit-logs/` dengan search (action/device/
  username) dan filter action persis, permission `audit.view`, read-only
  murni (POST/PUT/DELETE selalu 405, tidak ada jalur untuk mengubah/hapus
  lewat API maupun UI). **Halaman Audit Logs** (`/audit-logs`) menampilkan
  semuanya: waktu, user, action, device, IP, metadata.
- **RBAC penuh** — permission baru `alert.view` ditambahkan ke seed (semua
  role yang sebelumnya sudah `alert.manage` otomatis dapat `alert.view` juga).
  CRUD user sekarang lewat UI, bukan cuma Django admin: `GET/POST /api/users/`,
  `PATCH /api/users/{id}/` (ubah role/email), `.../activate/` |
  `.../deactivate/`, `.../reset-password/`, plus `GET /api/roles/` — semua
  permission `user.manage` (hanya dimiliki `SUPER_ADMIN` di seed default).
  Admin tidak bisa menonaktifkan akunnya sendiri (dicegah di backend, bukan
  cuma disembunyikan tombolnya). Setiap create/update/activate/deactivate/
  reset-password user tercatat di audit log dengan `target_user_id`.
  **Halaman Users** (`/users`) — form tambah user + role, tabel dengan ubah
  role inline, Aktifkan/Nonaktifkan, Reset Password (modal input password
  baru), badge status.
- Ditemukan 1 bug nyata di test suite lama (bukan di aplikasi): satu test
  Phase 2 hardcode `device_id == "SD-LPT-000001"`, padahal `device_id`
  diturunkan dari sequence PK Postgres yang **tidak** ikut ter-rollback antar
  transaksi test — setelah cukup banyak device asli dibuat sepanjang sesi
  pengembangan (termasuk semua testing Live Screen), assert itu akhirnya
  gagal. Diperbaiki dengan assert format (`SD-LPT-\d{6}`) alih-alih nilai
  literal.
- Diuji end-to-end lewat browser sungguhan (bukan cuma pytest): device asli
  dibuat, dikirim metric CPU 97% lewat endpoint agent sungguhan → alert
  CRITICAL muncul real-time (badge bell + halaman Alerts) → acknowledge →
  resolve, semuanya lewat klik UI. Users page diuji end-to-end: buat user →
  login dengan password yang baru dibuat → ubah role → nonaktifkan →
  aktifkan → reset password → login lagi dengan password baru — semua
  tercatat benar di halaman Audit Logs.
- 22 pytest baru (10 alerts, 4 audit, 8 user-management) — total 71 test,
  semua passed.

## Apa yang sudah berfungsi di Phase 8 (security hardening, testing, deployment, packaging)

- **Git & CI**: repo di-`git init` untuk pertama kalinya (belum pernah jadi git repo sebelum ini), commit awal berisi seluruh Phase 1-7. `.github/workflows/ci.yml` — dua job: `backend-tests` (Postgres+Redis service container, jalankan `pytest`) dan `frontend-build` (`npm ci && npm run build`), jalan otomatis begitu repo ini di-push ke GitHub/GitLab.
- **Bug nyata ditemukan & diperbaiki saat audit rate-limiting**: `DeviceUser` (stand-in `request.user` untuk request yang diautentikasi device token) selama ini punya `pk = None` yang sama untuk **semua** device — akibatnya DRF throttle (yang nge-key rate limit berdasarkan `request.user.pk`) menganggap seluruh device di fleet berbagi **satu** kuota rate-limit bersama, bukan satu kuota per device. Diperbaiki dengan mengisi `pk` dari device yang sebenarnya. Juga ditambahkan `UserRateThrottle` (300/min) sebagai baseline untuk endpoint yang belum punya `throttle_scope` sendiri (Alerts, Users, Audit Logs) — sebelumnya endpoint-endpoint itu sama sekali tidak dibatasi.
- `python manage.py check --deploy` sudah bersih di `config.settings.production` (satu-satunya warning hanya muncul kalau memang sengaja dites pakai secret key lemah).
- **`config/settings/production.py`** diperkuat: WhiteNoise (serve static Django admin langsung dari Daphne, tanpa volume statis terpisah), `CSRF_TRUSTED_ORIGINS`, `SECURE_PROXY_SSL_HEADER` (perlu karena TLS nanti terminasi di nginx, bukan di Daphne), dan flag `DJANGO_HTTPS_ENABLED` — sengaja default `false` karena nginx yang disiapkan belum punya sertifikat TLS sungguhan (belum ada domain produksi); mengaktifkan `SECURE_SSL_REDIRECT` tanpa TLS asli justru bikin redirect loop, bukan lebih aman. Sentry (`sentry-sdk`, sudah lama ada di `requirements/prod.txt` tapi belum pernah dipakai) sekarang benar-benar diinisialisasi, tapi no-op sampai `SENTRY_DSN` diisi.
- **Docker production, generik** (belum di-deploy ke server sungguhan — belum ada server tujuan): `backend/Dockerfile.prod` (hanya `requirements/prod.txt`, tanpa debug_toolbar/pytest/dst., jalankan `daphne` bukan `runserver`), `frontend/Dockerfile.prod` (multi-stage: build Vite lalu di-serve nginx), `nginx/conf.d/default.conf` (satu pintu masuk port 80: `/api`, `/admin`, `/static` ke backend, `/ws` ke backend dengan header upgrade yang benar untuk WebSocket, sisanya ke frontend), `docker-compose.prod.yml` (postgres/redis tanpa port ke host, image di-build sekali/immutable, tanpa bind-mount source). Frontend sekarang fallback ke path relatif (`/api`, dan `ws(s)://<host saat ini>/ws`) kalau env var Vite tidak di-set — supaya build produksi otomatis ikut domain apa pun tanpa perlu di-hardcode saat build.
- Diuji sungguhan di komputer ini (bukan cuma baca konfigurasi): seluruh stack production (5 container: postgres, redis, backend, frontend, nginx) di-build dan dijalankan di project Docker terpisah supaya tidak bentrok dengan stack dev yang sedang berjalan, lalu diverifikasi lewat request asli — halaman React ke-serve, login JWT lewat `/api/` berhasil, Django admin + static file (WhiteNoise) ke-serve dengan benar, dan WebSocket `/ws/dashboard/` berhasil upgrade lewat nginx sampai ke Daphne. Semua container & image test dibersihkan setelahnya.
- **Agent dikemas jadi `.exe`** (`agent/SentinelDeskAgent.spec`, PyInstaller, `agent/requirements-build.txt` terpisah dari runtime deps): satu file `.exe`, tanpa jendela console, semua dependency native (winsdk, aiortc, av/PyAV, tkinter) berhasil ter-bundle di percobaan build pertama. Ditemukan & diperbaiki bug nyata sebelum build: `AGENT_DIR`/`LOG_DIR` sebelumnya dihitung dari `__file__`, yang begitu di-freeze PyInstaller malah mengarah ke folder ekstraksi sementara — `.env`/`credentials.dat` akan "hilang" tiap proses berhenti. Diperbaiki supaya memakai lokasi `.exe` yang sebenarnya (`sys.executable`) saat frozen.
- **Auto-start saat login** (`agent/src/services/autostart.py`) — `.exe` mendaftarkan dirinya ke `HKCU\...\Run` (registry per-user, tanpa perlu admin) setiap kali berhasil jalan, jadi otomatis benar lagi kalau lokasi file berubah. `--uninstall-autostart` untuk melepas pendaftaran.
- Diuji dengan `.exe` sungguhan (bukan cuma `python src/main.py`): dijalankan langsung dari `dist/SentinelDeskAgent.exe`, berhasil enroll device asli, key registry auto-start beneran muncul dan menunjuk ke path exe yang benar, dan setelah restart backend (menemukan bug `DeviceUser` di atas lewat testing ini juga) metrics loop berjalan stabil beberapa siklus berturut-turut. Device test, kredensial, dan key registry dibersihkan setelahnya.
- Ketemu satu kuirk operasional (bukan bug aplikasi): Django `runserver` di dalam container dev sesekali tidak auto-reload saat file di-edit lewat bind mount di Docker Desktop/Windows (kelas masalah yang sama dengan kenapa Vite butuh `usePolling` — lihat Phase Docker) — kalau perubahan kode tidak kelihatan efeknya, `docker compose restart backend` menyelesaikannya.

## Testing cepat (manual)

```bash
# Login
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<password anda>"}'

# Pakai access token dari response di atas
curl http://localhost:8000/api/auth/me/ -H "Authorization: Bearer <access_token>"
```

Atau langsung buka `http://localhost:5173/login` di browser.

## Testing otomatis

```bash
docker compose exec backend pytest
```

(Test suite akan ditambahkan bertahap seiring fitur setiap phase — lihat
`docs/roadmap.md`.)

## Catatan Keamanan

- Jangan commit `.env` — hanya `.env.example` yang masuk git.
- `SECRET_KEY`, kredensial database, dan token JWT tidak pernah di-hardcode.
- Semua permission dicek ulang di backend (DRF permission class), frontend
  hanya mengatur tampilan.
- Audit log bersifat read-only di admin (tidak bisa diedit/dihapus lewat UI).
