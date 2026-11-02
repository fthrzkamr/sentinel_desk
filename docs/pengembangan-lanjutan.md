# Rencana Pengembangan Lanjutan (Post-Phase 8)

Dokumen ini mencatat daftar temuan teknis (*Quick Wins*) dan fitur pengembangan lanjutan untuk **SentinelDesk** beserta status pengerjaannya.

Legenda Status:
- ✅ **Selesai** — Sudah diimplementasikan dan lulus pengujian
- 🔄 **Sedang Dikerjakan** — Sedang dalam proses implementasi
- ⏳ **Belum Dikerjakan** — Antrean pengembangan berikutnya

---

## Tahap 1: Perbaikan Cepat & Stabilitas Inti (*Quick Wins*)

Fokus pada perbaikan celah konfigurasi, konsistensi cache, *real-time broadcast* WebSocket, serta ketahanan pengiriman data di sisi Agent.

| No | Item Pengembangan | Lokasi File Utama | Status |
|---|---|---|---|
| 1.1 | **Sinkronisasi Cache `SystemSettings` (`data_exfil_min_local_files`)**<br>Menambahkan `data_exfil_min_local_files` ke `_CACHED_FIELDS` dan `defaults` pada `SystemSettings.get_solo()` serta `config/settings/base.py` agar perubahan threshold dari UI Settings tidak ter-reset saat dibaca dari Redis cache. | `backend/apps/system_settings/models.py`<br>`backend/config/settings/base.py`<br>`backend/apps/system_settings/tests.py` | ✅ Selesai |
| 1.2 | **Penambahan `celery_worker` & `celery_beat` di Stack Production**<br>Menambahkan service `celery_worker` dan `celery_beat` ke `docker-compose.prod.yml` agar deteksi device *offline* otomatis (`mark_stale_devices_offline`) serta pembersihan retensi data (`prune_old_metrics` & `prune_old_activity`) berjalan di server produksi. | `docker-compose.prod.yml` | ✅ Selesai |
| 1.3 | **Real-Time WebSocket Broadcast untuk Semua Kategori Alert**<br>Menambahkan pemanggilan `broadcast_alert_triggered()` / `broadcast_alert_updated()` saat alert aktivitas & keamanan (`USB`, `DATA_EXFIL`, `SUSPICIOUS_URL`, `OUT_OF_HOURS`, `SYSTEM_ERROR`, `NEW_SOFTWARE`) terpicu atau *auto-resolve*, serta auto-refresh daftar alert di `AlertsView.vue`. | `backend/apps/monitoring/broadcast.py`<br>`backend/apps/device_activity/views.py`<br>`backend/apps/software/views.py`<br>`frontend/src/stores/monitoring.js`<br>`frontend/src/views/alerts/AlertsView.vue` | ✅ Selesai |
| 1.4 | **Ketahanan Sync Data Aktivitas di Agent (*Commit After Send*)**<br>Memastikan buffer data di Agent (`AppUsageTracker`, `IdleActivityTracker`, `FileActivityWatcher`, `BrowserHistoryTracker`, `SystemErrorTracker`, `UsbWatcher`) tidak hilang/terbuang apabila pengiriman HTTP ke backend gagal karena gangguan jaringan sementara. | `agent/src/main.py`<br>`agent/src/monitoring/*.py` | ✅ Selesai |

---

## Tahap 2: Notifikasi Eksternal & Eskalasi Insiden

Agar tim IT langsung mengetahui insiden kritis meskipun sedang tidak membuka dashboard web.

| No | Item Pengembangan | Deskripsi | Status |
|---|---|---|---|
| 2.1 | **Integrasi Webhook / Telegram / Email** | Pengaturan kanal notifikasi di halaman **Settings** (Bot Token/Chat ID Telegram, URL Webhook Slack/Teams/Discord, atau SMTP Email) beserta validasi field berpasangan & format email. | ✅ Selesai |
| 2.2 | **Pengiriman Alert Kritis Asinkron via Celery** | Task Celery otomatis (`send_critical_alert_notification_task`) untuk mengirim notifikasi saat alert `CRITICAL` (`DATA_EXFIL`, `SUSPICIOUS_URL`, `SYSTEM_ERROR`, `NEW_SOFTWARE` ilegal, dll.) baru terbentuk atau tereskalasi dari `WARNING` ke `CRITICAL`. | ✅ Selesai |
| 2.3 | **Fitur Test Notification di UI Settings** | Endpoint `POST /api/settings/test-notification/` dan tombol **"Kirim Pesan Tes"** di halaman Settings untuk menguji pengiriman ke Telegram/Webhook/Email secara langsung sebelum disimpan. | ✅ Selesai |

---

## Tahap 3: Pelaporan (Reporting) & Optimasi Ringkasan Dashboard

Meningkatkan efisiensi pemantauan armada dan kebutuhan pelaporan audit.

| No | Item Pengembangan | Deskripsi | Status |
|---|---|---|---|
| 3.1 | **Endpoint Agregasi `GET /api/devices/dashboard-summary/`** | Menghitung total status (`ONLINE`, `OFFLINE`, `WARNING`, `CRITICAL`, `DISABLED`, `Pending Approval`) langsung lewat query agregat database agar akurat untuk >200 device. | ✅ Selesai |
| 3.2 | **Export CSV / Laporan Audit** | Tombol Export CSV pada halaman **Alerts**, **Audit Logs**, dan **Assets** (mendukung hingga `page_size=500` sesuai filter aktif) untuk kebutuhan pelaporan manajemen & audit kepatuhan. | ✅ Selesai |
| 3.3 | **Panel Compliance & High-Risk di Dashboard** | *Ditiadakan / Dihapus dari UI* atas evaluasi kebutuhan agar tampilan Dashboard tetap ringkas, bersih, dan fokus pada status realtime serta perangkat yang aktif. | ❌ Ditiadakan |

---

## Tahap 4: Manajemen Agent Jarak Jauh (Remote Config & OTA Auto-Update)

Memudahkan pengelolaan ratusan laptop tanpa harus mendatangi atau meremote perangkat satu per satu.

| No | Item Pengembangan | Deskripsi | Status |
|---|---|---|---|
| 4.1 | **HTTP Session Pooling di Agent** | Menggunakan `requests.Session()` di `agent/src/networking/client.py` untuk koneksi *Keep-Alive* yang lebih hemat resource dan stabil. | ✅ Selesai |
| 4.2 | **Dynamic Remote Policy / Agent Config** | Mengirim kebijakan monitoring dari server ke agent saat *heartbeat/metrics* sehingga admin bisa menyalakan/mematikan modul pemantauan (`screen`, `usb`, `file_activity`, `browser_history`, interval) langsung dari UI Dashboard. | ✅ Selesai |
| 4.3 | **Over-The-Air (OTA) Agent Auto-Update** | Manajemen upload rilis `.exe` baru di dashboard lengkap dengan validasi SHA-256 checksum agar agent dapat memperbarui versinya secara otomatis. | ✅ Selesai |

---

## Tahap 5: Peningkatan Live Screen (TURN Server & Multi-Monitor)

Memastikan fitur Live Screen dapat berjalan lintas jaringan/cabang dan mendukung banyak layar.

| No | Item Pengembangan | Deskripsi | Status |
|---|---|---|---|
| 5.1 | **Dukungan Konfigurasi TURN Server (`coturn`)** | Menambahkan konfigurasi ICE TURN server agar koneksi WebRTC tetap tembus saat laptop karyawan berada di balik Symmetric NAT / firewall ketat (WFH atau cabang berbeda). | ✅ Selesai |
| 5.2 | **Pemilihan Monitor (Multi-Monitor Selector)** | Opsi memilih layar (Monitor 1, Monitor 2, dst.) pada tab Live Screen jika perangkat karyawan menggunakan monitor eksternal. | ✅ Selesai |

---

## Tahap 6: Keamanan Lanjutan & Otomasi CI/CD Agent

Memperkuat keamanan akun administrator dan menjaga kualitas kode Agent di pipeline CI.

| No | Item Pengembangan | Deskripsi | Status |
|---|---|---|---|
| 6.1 | **Two-Factor Authentication (2FA / TOTP) untuk Admin** | Verifikasi OTP berbasis aplikasi autentikator untuk akun admin, terutama yang memiliki izin sensitif (`monitoring.live_screen`, `user.manage`). | ✅ Selesai |
| 6.2 | **Rotasi Token Perangkat & Kebijakan Retensi Alert/Audit** | Mekanisme pembaruan berkala `DeviceCredential` serta pembersihan terjadwal untuk alert lama yang sudah `RESOLVED`. | ✅ Selesai |
| 6.3 | **Unit Test & Build Pipeline untuk Agent di GitHub Actions** | Menambahkan job pengujian otomatis untuk kode `agent/` di `.github/workflows/ci.yml`. | ✅ Selesai |

---

## Tahap 7: Remote Control & Remote Assistance (Mouse, Keyboard, Clipboard, & Pintasan OS)

Mengubah Live Screen dari yang sebelumnya hanya memantau (*view-only*) menjadi kendali interaktif penuh dua arah layaknya AnyDesk / TeamViewer / RustDesk langsung dari Web Browser.

| No | Item Pengembangan | Deskripsi | Status |
|---|---|---|---|
| 7.1 | **WebRTC DataChannel Bi-Directional Input Relay** | Membuka saluran WebRTC `RTCDataChannel` ("control") berkecepatan tinggi P2P (latensi sub-10ms) dengan fallback ke WebSocket signaling untuk menyalurkan event mouse, keyboard, dan pintasan dari browser admin ke agent. | ✅ Selesai |
| 7.2 | **Native Windows Input Injection (`user32.dll` / `SendInput`)** | Mengeksekusi pergerakan kursor mouse dengan koordinat normalisasi presisi tinggi, klik mouse (kiri, kanan, tengah, double-click, scroll wheel), keystroke, dan karakter Unicode melalui Windows Win32 API resmi tanpa dependensi pihak ketiga yang berat. | ✅ Selesai |
| 7.3 | **Interactive Remote Toolbar & Mode Switch di UI** | Menambahkan tombol saklar `[ Mode: Pantau (View) | Kendali (Control) ]`, bilah pintasan cepat (`Win + R`, `Win + D`, `Alt + Tab`, `Ctrl + Shift + Esc`), modal sinkronisasi teks/clipboard, dan audit logging otomatis (`livescreen.control_enabled` / `livescreen.control_disabled`). | ✅ Selesai |

