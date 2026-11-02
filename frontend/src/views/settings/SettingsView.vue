<script setup>
import { onMounted, reactive, ref } from 'vue'
import QRCode from 'qrcode'

import StatusModal from '@/components/StatusModal.vue'
import api from '@/services/api'
import {
  getSystemSettings,
  sendTestNotification,
  updateSystemSettings,
  uploadAgentBinary,
} from '@/services/settings'
import {
  addSoftwareWhitelistEntry,
  deleteSoftwareWhitelistEntry,
  listSoftwareWhitelist,
} from '@/services/software'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const form = reactive({
  cpu_warning_percent: null,
  cpu_critical_percent: null,
  ram_warning_percent: null,
  ram_critical_percent: null,
  disk_warning_percent: null,
  disk_critical_percent: null,
  battery_critical_percent: null,
  device_offline_threshold_seconds: null,
  device_metric_retention_days: null,
  activity_retention_days: null,
  alert_retention_days: 60,
  audit_retention_days: 180,
  data_exfil_min_local_files: null,
  work_hours_start: null,
  work_hours_end: null,
  notifications_enabled: false,
  telegram_bot_token: '',
  telegram_chat_id: '',
  webhook_url: '',
  notification_emails: '',
  agent_metrics_interval_seconds: 15,
  agent_screen_monitor_enabled: true,
  agent_usb_monitor_enabled: true,
  agent_app_usage_monitor_enabled: true,
  browser_history_monitor_enabled: true,
  agent_browser_history_monitor_enabled: true,
  agent_file_activity_monitor_enabled: true,
  agent_idle_activity_monitor_enabled: true,
  agent_system_error_monitor_enabled: true,
  agent_auto_update_enabled: false,
  agent_latest_version: '',
  agent_download_url: '',
  agent_sha256: '',
  stun_server_url: 'stun:stun.l.google.com:19302',
  turn_server_enabled: false,
  turn_server_url: '',
  turn_username: '',
  turn_credential: '',
})

const isLoading = ref(true)
const isSaving = ref(false)
const isTestingNotification = ref(false)
const testNotificationResult = reactive({ message: '', isError: false })
const errorMessage = ref('')
const fieldErrors = ref({})
const updatedAt = ref(null)
const status = reactive({ open: false, variant: 'success', title: '', message: '' })

const uploadVersion = ref('')
const uploadFile = ref(null)
const isUploadingBinary = ref(false)
const uploadBinaryError = ref('')
const uploadBinarySuccess = ref('')

function handleFileChange(event) {
  const files = event.target.files
  uploadFile.value = files.length > 0 ? files[0] : null
}

async function handleUploadBinary() {
  if (!uploadVersion.value.trim() || !uploadFile.value) {
    uploadBinaryError.value = 'Versi dan file binary agent .exe wajib diisi.'
    return
  }
  isUploadingBinary.value = true
  uploadBinaryError.value = ''
  uploadBinarySuccess.value = ''
  try {
    const formData = new FormData()
    formData.append('version', uploadVersion.value.trim())
    formData.append('file', uploadFile.value)
    const { data } = await uploadAgentBinary(formData)
    uploadBinarySuccess.value = `Rilis versi ${data.version} berhasil diunggah (SHA-256: ${data.sha256.substring(0, 12)}...). OTA update siap didistribusikan.`
    form.agent_latest_version = data.version
    form.agent_sha256 = data.sha256
    form.agent_download_url = data.download_url
    form.agent_auto_update_enabled = true
    uploadVersion.value = ''
    uploadFile.value = null
  } catch (err) {
    uploadBinaryError.value = err.response?.data?.detail || 'Gagal mengunggah binary agent.'
  } finally {
    isUploadingBinary.value = false
  }
}

async function fetchSettings() {
  isLoading.value = true
  try {
    const { data } = await getSystemSettings()
    Object.assign(form, data)
    updatedAt.value = data.updated_at
  } catch {
    errorMessage.value = 'Gagal memuat pengaturan sistem.'
  } finally {
    isLoading.value = false
  }
}

const whitelistEntries = ref([])
const isWhitelistLoading = ref(false)
const newWhitelistName = ref('')
const isAddingWhitelist = ref(false)
const whitelistError = ref('')

async function fetchWhitelist() {
  if (!auth.hasPermission('software.manage')) return
  isWhitelistLoading.value = true
  try {
    const { data } = await listSoftwareWhitelist()
    whitelistEntries.value = data
  } catch {
    whitelistError.value = 'Gagal memuat whitelist.'
  } finally {
    isWhitelistLoading.value = false
  }
}

async function handleAddWhitelist() {
  const name = newWhitelistName.value.trim()
  if (!name) return
  isAddingWhitelist.value = true
  whitelistError.value = ''
  try {
    await addSoftwareWhitelistEntry(name)
    newWhitelistName.value = ''
    await fetchWhitelist()
  } catch (error) {
    whitelistError.value = error.response?.data?.name?.[0] || 'Gagal menambah software ke whitelist.'
  } finally {
    isAddingWhitelist.value = false
  }
}

async function handleRemoveWhitelist(entry) {
  try {
    await deleteSoftwareWhitelistEntry(entry.id)
    whitelistEntries.value = whitelistEntries.value.filter((e) => e.id !== entry.id)
  } catch {
    whitelistError.value = 'Gagal menghapus dari whitelist.'
  }
}

onMounted(() => {
  fetchSettings()
  fetchWhitelist()
  check2FAStatus()
})

const twoFactor = reactive({
  enabled: false,
  setupStep: false,
  secret: '',
  otpauth_url: '',
  qrDataUrl: '',
  code: '',
  disablePassword: '',
  showDisableModal: false,
  isProcessing: false,
  error: '',
})

async function check2FAStatus() {
  twoFactor.enabled = Boolean(auth.user?.totp_enabled)
}

async function start2FASetup() {
  twoFactor.isProcessing = true
  twoFactor.error = ''
  try {
    const { data } = await api.get('/auth/2fa/setup/')
    twoFactor.secret = data.secret
    twoFactor.otpauth_url = data.otpauth_url
    twoFactor.enabled = data.totp_enabled
    twoFactor.qrDataUrl = await QRCode.toDataURL(data.otpauth_url, { width: 180, margin: 1 })
    twoFactor.setupStep = true
    twoFactor.code = ''
  } catch (err) {
    twoFactor.error = err.response?.data?.detail || 'Gagal memulai penyiapan 2FA.'
  } finally {
    twoFactor.isProcessing = false
  }
}

async function verifyAndEnable2FA() {
  if (twoFactor.code.length < 6) return
  twoFactor.isProcessing = true
  twoFactor.error = ''
  try {
    await api.post('/auth/2fa/verify/', { code: twoFactor.code, secret: twoFactor.secret })
    twoFactor.enabled = true
    twoFactor.setupStep = false
    if (auth.user) auth.user.totp_enabled = true
    status.variant = 'success'
    status.title = '2FA Aktif'
    status.message = 'Autentikasi dua langkah (2FA) berhasil diaktifkan untuk akun Anda.'
    status.open = true
  } catch (err) {
    twoFactor.error = err.response?.data?.detail || 'Kode 2FA tidak valid. Periksa jam ponsel Anda.'
  } finally {
    twoFactor.isProcessing = false
  }
}

async function disable2FA() {
  twoFactor.isProcessing = true
  twoFactor.error = ''
  try {
    await api.post('/auth/2fa/disable/', { password: twoFactor.disablePassword })
    twoFactor.enabled = false
    twoFactor.showDisableModal = false
    twoFactor.disablePassword = ''
    if (auth.user) auth.user.totp_enabled = false
    status.variant = 'success'
    status.title = '2FA Dinonaktifkan'
    status.message = 'Autentikasi dua langkah (2FA) telah dimatikan.'
    status.open = true
  } catch (err) {
    twoFactor.error = err.response?.data?.detail || 'Password salah.'
  } finally {
    twoFactor.isProcessing = false
  }
}

async function handleSave() {
  isSaving.value = true
  errorMessage.value = ''
  fieldErrors.value = {}
  try {
    const { data } = await updateSystemSettings(form)
    Object.assign(form, data)
    updatedAt.value = data.updated_at
    status.variant = 'success'
    status.title = 'Pengaturan disimpan'
    status.message = 'Perubahan langsung berlaku, tanpa perlu restart.'
    status.open = true
  } catch (error) {
    const data = error.response?.data
    if (data && typeof data === 'object') {
      fieldErrors.value = data
      errorMessage.value = 'Ada input yang belum valid — lihat catatan di bawah tiap field.'
    } else {
      errorMessage.value = 'Gagal menyimpan pengaturan.'
    }
  } finally {
    isSaving.value = false
  }
}

function fieldError(key) {
  const err = fieldErrors.value[key]
  return Array.isArray(err) ? err[0] : err
}

async function handleTestNotification() {
  isTestingNotification.value = true
  testNotificationResult.message = ''
  testNotificationResult.isError = false
  try {
    const { data } = await sendTestNotification({
      telegram_bot_token: form.telegram_bot_token,
      telegram_chat_id: form.telegram_chat_id,
      webhook_url: form.webhook_url,
      notification_emails: form.notification_emails,
    })
    const errKeys = Object.keys(data.errors || {})
    if (errKeys.length > 0) {
      testNotificationResult.isError = true
      testNotificationResult.message = `${data.detail} (Gagal pada: ${errKeys.join(', ')})`
    } else {
      testNotificationResult.isError = false
      testNotificationResult.message = data.detail
    }
  } catch (error) {
    testNotificationResult.isError = true
    const errData = error.response?.data
    const errDetail = errData?.detail || 'Gagal mengirim pesan tes.'
    const channelErrors = errData?.errors
      ? Object.entries(errData.errors)
          .map(([k, v]) => `${k}: ${v}`)
          .join('; ')
      : ''
    testNotificationResult.message = channelErrors ? `${errDetail} (${channelErrors})` : errDetail
  } finally {
    isTestingNotification.value = false
  }
}
</script>

<template>
  <div class="max-w-3xl space-y-6">
    <div>
      <h1 class="text-xl font-semibold text-slate-800">Settings</h1>
      <p class="mt-1 text-sm text-slate-500">
        Threshold status device dan alert. Berlaku langsung ke semua device begitu disimpan — tidak perlu restart
        backend maupun agent.
      </p>
    </div>

    <div v-if="isLoading" class="rounded-xl bg-white p-6 text-center text-slate-400 shadow-sm ring-1 ring-slate-900/5">
      Memuat data...
    </div>

    <form v-else class="space-y-6" @submit.prevent="handleSave">
      <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <h2 class="text-sm font-semibold text-slate-700">Threshold CPU</h2>
        <div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Warning (%)</label>
            <input v-model.number="form.cpu_warning_percent" type="number" min="0" max="100" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('cpu_warning_percent')" class="mt-1 text-xs text-red-600">{{ fieldError('cpu_warning_percent') }}</p>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Critical (%)</label>
            <input v-model.number="form.cpu_critical_percent" type="number" min="0" max="100" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('cpu_critical_percent')" class="mt-1 text-xs text-red-600">{{ fieldError('cpu_critical_percent') }}</p>
          </div>
        </div>
      </div>

      <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <h2 class="text-sm font-semibold text-slate-700">Threshold RAM</h2>
        <div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Warning (%)</label>
            <input v-model.number="form.ram_warning_percent" type="number" min="0" max="100" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('ram_warning_percent')" class="mt-1 text-xs text-red-600">{{ fieldError('ram_warning_percent') }}</p>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Critical (%)</label>
            <input v-model.number="form.ram_critical_percent" type="number" min="0" max="100" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('ram_critical_percent')" class="mt-1 text-xs text-red-600">{{ fieldError('ram_critical_percent') }}</p>
          </div>
        </div>
      </div>

      <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <h2 class="text-sm font-semibold text-slate-700">Threshold Disk</h2>
        <div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Warning (%)</label>
            <input v-model.number="form.disk_warning_percent" type="number" min="0" max="100" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('disk_warning_percent')" class="mt-1 text-xs text-red-600">{{ fieldError('disk_warning_percent') }}</p>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Critical (%)</label>
            <input v-model.number="form.disk_critical_percent" type="number" min="0" max="100" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('disk_critical_percent')" class="mt-1 text-xs text-red-600">{{ fieldError('disk_critical_percent') }}</p>
          </div>
        </div>
      </div>

      <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <h2 class="text-sm font-semibold text-slate-700">Baterai &amp; Konektivitas</h2>
        <div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Battery Critical (%, saat tidak charging)</label>
            <input v-model.number="form.battery_critical_percent" type="number" min="0" max="100" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('battery_critical_percent')" class="mt-1 text-xs text-red-600">{{ fieldError('battery_critical_percent') }}</p>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Device dianggap Offline setelah (detik)</label>
            <input v-model.number="form.device_offline_threshold_seconds" type="number" min="10" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('device_offline_threshold_seconds')" class="mt-1 text-xs text-red-600">{{ fieldError('device_offline_threshold_seconds') }}</p>
          </div>
        </div>
      </div>

      <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <h2 class="text-sm font-semibold text-slate-700">Retensi Data</h2>
        <div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Simpan histori metric selama (hari)</label>
            <input v-model.number="form.device_metric_retention_days" type="number" min="1" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('device_metric_retention_days')" class="mt-1 text-xs text-red-600">{{ fieldError('device_metric_retention_days') }}</p>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">
              Simpan App Usage/Browsing/File selama (hari)
            </label>
            <input v-model.number="form.activity_retention_days" type="number" min="1" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('activity_retention_days')" class="mt-1 text-xs text-red-600">{{ fieldError('activity_retention_days') }}</p>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Simpan riwayat Alert Resolved selama (hari)</label>
            <input v-model.number="form.alert_retention_days" type="number" min="1" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('alert_retention_days')" class="mt-1 text-xs text-red-600">{{ fieldError('alert_retention_days') }}</p>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Simpan riwayat Audit Log selama (hari)</label>
            <input v-model.number="form.audit_retention_days" type="number" min="1" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('audit_retention_days')" class="mt-1 text-xs text-red-600">{{ fieldError('audit_retention_days') }}</p>
          </div>
        </div>
      </div>

      <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <h2 class="text-sm font-semibold text-slate-700">Jam Kerja &amp; Deteksi Kebocoran Data</h2>
        <p class="mt-1 text-xs text-slate-400">
          Aktivitas (app usage, browsing, file) di luar jam ini akan memicu alert "Aktivitas di Luar Jam
          Kerja". Isi 0-23 (format 24 jam, sesuai zona waktu server).
        </p>
        <div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Jam Mulai Kerja</label>
            <input v-model.number="form.work_hours_start" type="number" min="0" max="23" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('work_hours_start')" class="mt-1 text-xs text-red-600">{{ fieldError('work_hours_start') }}</p>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Jam Selesai Kerja</label>
            <input v-model.number="form.work_hours_end" type="number" min="0" max="23" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('work_hours_end')" class="mt-1 text-xs text-red-600">{{ fieldError('work_hours_end') }}</p>
          </div>
          <div class="sm:col-span-2">
            <label class="mb-1 block text-xs font-medium text-slate-600">
              Minimum perubahan file lokal (10 menit terakhir) sebelum kunjungan Cloud Storage memicu alert DATA_EXFIL
            </label>
            <input v-model.number="form.data_exfil_min_local_files" type="number" min="1" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 sm:max-w-xs" />
            <p v-if="fieldError('data_exfil_min_local_files')" class="mt-1 text-xs text-red-600">{{ fieldError('data_exfil_min_local_files') }}</p>
          </div>
        </div>
      </div>

      <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 class="text-sm font-semibold text-slate-700">Notifikasi Eksternal (Alert Kritis)</h2>
            <p class="mt-1 text-xs text-slate-400">
              Kirim peringatan otomatis lewat Telegram, Webhook (Slack/Discord/Teams), atau Email setiap kali
              terjadi insiden berstatus <strong>CRITICAL</strong> (seperti indikasi kebocoran data, URL phishing,
              software ilegal, atau pemakaian resource kritis).
            </p>
          </div>
          <label class="inline-flex cursor-pointer items-center gap-2 text-xs font-medium text-slate-700">
            <input
              v-model="form.notifications_enabled"
              type="checkbox"
              class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
            Aktifkan Notifikasi
          </label>
        </div>

        <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Telegram Bot Token</label>
            <input
              v-model="form.telegram_bot_token"
              type="password"
              autocomplete="off"
              placeholder="123456789:ABCdefGHIjklMNO..."
              class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
            <p v-if="fieldError('telegram_bot_token')" class="mt-1 text-xs text-red-600">{{ fieldError('telegram_bot_token') }}</p>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Telegram Chat ID</label>
            <input
              v-model="form.telegram_chat_id"
              type="text"
              placeholder="mis. -1001234567890"
              class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
            <p v-if="fieldError('telegram_chat_id')" class="mt-1 text-xs text-red-600">{{ fieldError('telegram_chat_id') }}</p>
          </div>
          <div class="sm:col-span-2">
            <label class="mb-1 block text-xs font-medium text-slate-600">Webhook URL (Slack / Discord / Microsoft Teams / Custom)</label>
            <input
              v-model="form.webhook_url"
              type="url"
              placeholder="https://hooks.slack.com/services/... atau https://discord.com/api/webhooks/..."
              class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
            <p v-if="fieldError('webhook_url')" class="mt-1 text-xs text-red-600">{{ fieldError('webhook_url') }}</p>
          </div>
          <div class="sm:col-span-2">
            <label class="mb-1 block text-xs font-medium text-slate-600">Email Penerima (pisahkan dengan koma)</label>
            <input
              v-model="form.notification_emails"
              type="text"
              placeholder="it-security@perusahaan.com, admin@perusahaan.com"
              class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
            <p v-if="fieldError('notification_emails')" class="mt-1 text-xs text-red-600">{{ fieldError('notification_emails') }}</p>
          </div>
        </div>

        <div class="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
          <p
            v-if="testNotificationResult.message"
            class="text-xs font-medium"
            :class="testNotificationResult.isError ? 'text-red-600' : 'text-emerald-600'"
          >
            {{ testNotificationResult.message }}
          </p>
          <span v-else class="text-xs text-slate-400">
            Uji pengiriman pesan ke kanal yang diisi di atas sebelum menyimpan.
          </span>
          <button
            type="button"
            :disabled="isTestingNotification"
            class="rounded-lg border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            @click="handleTestNotification"
          >
            {{ isTestingNotification ? 'Mengirim Tes...' : 'Kirim Pesan Tes' }}
          </button>
        </div>
      </div>

      <!-- Agent Remote Policy -->
      <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <h2 class="text-sm font-semibold text-slate-700">Kebijakan Pemantauan Agent (Remote Policy)</h2>
        <p class="mt-1 text-xs text-slate-400">
          Atur interval pengiriman dan aktifkan/nonaktifkan modul monitoring di seluruh laptop karyawan secara remote.
          Perubahan otomatis diterapkan oleh Agent saat mengirim metrik berikutnya tanpa perlu sentuh perangkat fisik.
        </p>

        <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Interval Pengiriman Metrik (detik)</label>
            <input
              v-model.number="form.agent_metrics_interval_seconds"
              type="number"
              min="5"
              max="300"
              class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
            <p class="mt-1 text-xs text-slate-400">Default 15 detik. Nilai lebih tinggi menghemat bandwidth &amp; baterai.</p>
          </div>
        </div>

        <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label class="flex items-center gap-2.5 rounded-lg border border-slate-200 p-3 text-sm cursor-pointer hover:bg-slate-50">
            <input v-model="form.agent_screen_monitor_enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
            <div>
              <div class="font-medium text-slate-700">Live Screen Monitoring</div>
              <div class="text-xs text-slate-400">Koneksi signaling WebRTC untuk pantau layar</div>
            </div>
          </label>

          <label class="flex items-center gap-2.5 rounded-lg border border-slate-200 p-3 text-sm cursor-pointer hover:bg-slate-50">
            <input v-model="form.agent_usb_monitor_enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
            <div>
              <div class="font-medium text-slate-700">USB Storage Monitoring</div>
              <div class="text-xs text-slate-400">Deteksi colok flashdisk &amp; copy file</div>
            </div>
          </label>

          <label class="flex items-center gap-2.5 rounded-lg border border-slate-200 p-3 text-sm cursor-pointer hover:bg-slate-50">
            <input v-model="form.agent_app_usage_monitor_enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
            <div>
              <div class="font-medium text-slate-700">App Usage Tracker</div>
              <div class="text-xs text-slate-400">Durasi pemakaian software aktif</div>
            </div>
          </label>

          <label class="flex items-center gap-2.5 rounded-lg border border-slate-200 p-3 text-sm cursor-pointer hover:bg-slate-50">
            <input v-model="form.agent_browser_history_monitor_enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
            <div>
              <div class="font-medium text-slate-700">Browser History Tracker</div>
              <div class="text-xs text-slate-400">Audit domain &amp; URL mencurigakan</div>
            </div>
          </label>

          <label class="flex items-center gap-2.5 rounded-lg border border-slate-200 p-3 text-sm cursor-pointer hover:bg-slate-50">
            <input v-model="form.agent_file_activity_monitor_enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
            <div>
              <div class="font-medium text-slate-700">File Activity Watcher</div>
              <div class="text-xs text-slate-400">Deteksi file dibuat/diubah/dihapus</div>
            </div>
          </label>

          <label class="flex items-center gap-2.5 rounded-lg border border-slate-200 p-3 text-sm cursor-pointer hover:bg-slate-50">
            <input v-model="form.agent_idle_activity_monitor_enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
            <div>
              <div class="font-medium text-slate-700">Idle Activity Tracker</div>
              <div class="text-xs text-slate-400">Waktu diam tanpa aktivitas keyboard/mouse</div>
            </div>
          </label>

          <label class="flex items-center gap-2.5 rounded-lg border border-slate-200 p-3 text-sm cursor-pointer hover:bg-slate-50">
            <input v-model="form.agent_system_error_monitor_enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
            <div>
              <div class="font-medium text-slate-700">System Error Tracker</div>
              <div class="text-xs text-slate-400">Event Viewer Windows BSOD &amp; disk warning</div>
            </div>
          </label>
        </div>
      </div>

      <!-- OTA Agent Auto-Update -->
      <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="text-sm font-semibold text-slate-700">Pembaruan Agent Jarak Jauh (OTA Auto-Update)</h2>
            <p class="mt-1 text-xs text-slate-400">
              Distribusikan pembaruan binary <code>SentinelDeskAgent.exe</code> secara otomatis ke seluruh laptop yang terhubung.
              Agent memverifikasi integritas checksum SHA-256 sebelum memperbarui diri.
            </p>
          </div>
          <label class="flex items-center gap-2 text-sm font-medium text-slate-700 cursor-pointer">
            <input
              v-model="form.agent_auto_update_enabled"
              type="checkbox"
              class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
            Aktifkan OTA Auto-Update
          </label>
        </div>

        <div class="mt-4 rounded-lg border border-slate-100 bg-slate-50/70 p-4 text-xs space-y-1.5">
          <div class="flex items-center justify-between">
            <span class="font-medium text-slate-600">Versi Rilis Saat Ini:</span>
            <span class="font-mono font-semibold text-slate-800">{{ form.agent_latest_version || 'Belum ada rilis terunggah' }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="font-medium text-slate-600">Download URL:</span>
            <span class="font-mono text-slate-600 truncate max-w-md">{{ form.agent_download_url || '-' }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="font-medium text-slate-600">Checksum SHA-256:</span>
            <span class="font-mono text-slate-600 truncate max-w-md">{{ form.agent_sha256 || '-' }}</span>
          </div>
        </div>

        <div class="mt-4 border-t border-slate-100 pt-4">
          <h3 class="text-xs font-semibold text-slate-700">Unggah Rilis Binary Agent Baru (.exe)</h3>
          <div class="mt-3 flex flex-wrap items-end gap-3">
            <div>
              <label class="mb-1 block text-xs font-medium text-slate-600">Nomor Versi Rilis</label>
              <input
                v-model="uploadVersion"
                type="text"
                placeholder="mis. 0.8.16"
                class="w-36 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium text-slate-600">File Executable (.exe)</label>
              <input
                type="file"
                accept=".exe"
                class="rounded-lg border border-slate-300 px-3 py-1 text-sm text-slate-600 file:mr-2 file:rounded-md file:border-0 file:bg-slate-100 file:px-2.5 file:py-1 file:text-xs file:font-semibold file:text-slate-700 hover:file:bg-slate-200"
                @change="handleFileChange"
              />
            </div>
            <button
              type="button"
              :disabled="isUploadingBinary || !uploadVersion.trim() || !uploadFile"
              class="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
              @click="handleUploadBinary"
            >
              {{ isUploadingBinary ? 'Mengunggah & Memvalidasi...' : 'Unggah & Siapkan OTA' }}
            </button>
          </div>
          <p v-if="uploadBinaryError" class="mt-2 text-xs font-medium text-red-600">{{ uploadBinaryError }}</p>
          <p v-if="uploadBinarySuccess" class="mt-2 text-xs font-medium text-emerald-600">{{ uploadBinarySuccess }}</p>
        </div>
      </div>

      <!-- TURN Server Configuration -->
      <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="text-sm font-semibold text-slate-700">Konfigurasi TURN Server (WebRTC ICE Live Screen)</h2>
            <p class="mt-1 text-xs text-slate-400">
              Relay server media WebRTC untuk memastikan streaming Live Screen dapat menembus Symmetric NAT dan firewall ketat
              saat karyawan bekerja dari luar kantor (WFH) atau cabang berbeda.
            </p>
          </div>
          <label class="flex items-center gap-2 text-sm font-medium text-slate-700 cursor-pointer">
            <input
              v-model="form.turn_server_enabled"
              type="checkbox"
              class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
            Aktifkan TURN Relay
          </label>
        </div>

        <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">STUN Server URL</label>
            <input
              v-model="form.stun_server_url"
              type="text"
              placeholder="stun:stun.l.google.com:19302"
              class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
            <p class="mt-1 text-xs text-slate-400">Default: stun:stun.l.google.com:19302</p>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">TURN Server URL (coturn)</label>
            <input
              v-model="form.turn_server_url"
              type="text"
              placeholder="turn:turn.domain.com:3478 atau turns:turn.domain.com:5349"
              class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
            <p class="mt-1 text-xs text-slate-400">Alamat host dan port server coturn.</p>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">TURN Username</label>
            <input
              v-model="form.turn_username"
              type="text"
              placeholder="username coturn"
              class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">TURN Credential / Password</label>
            <input
              v-model="form.turn_credential"
              type="password"
              placeholder="••••••••"
              class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>
        </div>
      </div>

      <p v-if="errorMessage" class="text-sm text-red-600">{{ errorMessage }}</p>

      <div class="flex items-center justify-between">
        <p class="text-xs text-slate-400">
          {{ updatedAt ? `Terakhir diubah: ${new Date(updatedAt).toLocaleString()}` : '' }}
        </p>
        <button type="submit" :disabled="isSaving" class="rounded-lg bg-brand-600 px-5 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60">
          {{ isSaving ? 'Menyimpan...' : 'Simpan Perubahan' }}
        </button>
      </div>
    </form>

    <!-- 2FA Authenticator Section -->
    <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-sm font-semibold text-slate-700">Autentikasi Dua Langkah (2FA / TOTP)</h2>
          <p class="mt-1 text-xs text-slate-500">
            Amankan akun administrator Anda dengan kode OTP 6-digit dari aplikasi authenticator (Google Authenticator, Microsoft Authenticator, atau Authy).
          </p>
        </div>
        <span
          class="rounded-full px-2.5 py-1 text-xs font-medium"
          :class="twoFactor.enabled ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-600/20' : 'bg-slate-100 text-slate-600'"
        >
          {{ twoFactor.enabled ? '2FA Aktif' : '2FA Nonaktif' }}
        </span>
      </div>

      <div v-if="twoFactor.error" class="mt-3 rounded-lg bg-red-50 p-2.5 text-xs text-red-600">
        {{ twoFactor.error }}
      </div>

      <!-- Setup Step: QR Code -->
      <div v-if="twoFactor.setupStep" class="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
        <h3 class="text-xs font-semibold text-slate-700">Langkah Penyiapan 2FA</h3>
        <p class="mt-1 text-xs text-slate-500">
          1. Pindai QR Code di bawah menggunakan aplikasi authenticator di ponsel Anda:
        </p>
        <div class="mt-3 flex flex-col sm:flex-row items-center gap-4">
          <div class="rounded-lg border border-slate-200 bg-white p-2">
            <img v-if="twoFactor.qrDataUrl" :src="twoFactor.qrDataUrl" alt="2FA QR Code" class="h-40 w-40" />
          </div>
          <div class="space-y-2 text-xs">
            <p class="text-slate-600">Atau masukkan kode rahasia secara manual jika kamera bermasalah:</p>
            <div class="rounded bg-slate-200 px-2 py-1 font-mono font-medium text-slate-800 select-all">
              {{ twoFactor.secret }}
            </div>
            <p class="text-slate-400">Tipe: Time-based (TOTP), 6 Digit, 30 Detik</p>
          </div>
        </div>

        <div class="mt-4 pt-3 border-t border-slate-200">
          <p class="text-xs font-medium text-slate-700 mb-1.5">2. Masukkan 6-digit kode OTP dari aplikasi untuk verifikasi:</p>
          <div class="flex gap-2 max-w-xs">
            <input
              v-model="twoFactor.code"
              type="text"
              maxlength="6"
              placeholder="000000"
              class="w-36 rounded-lg border border-slate-300 px-3 py-1.5 font-mono text-center text-sm tracking-widest focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
            <button
              type="button"
              :disabled="twoFactor.isProcessing || twoFactor.code.length < 6"
              class="rounded-lg bg-brand-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
              @click="verifyAndEnable2FA"
            >
              {{ twoFactor.isProcessing ? 'Verifikasi...' : 'Aktifkan' }}
            </button>
            <button
              type="button"
              class="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100"
              @click="twoFactor.setupStep = false"
            >
              Batal
            </button>
          </div>
        </div>
      </div>

      <!-- Action Buttons -->
      <div v-else class="mt-4 flex gap-2">
        <button
          v-if="!twoFactor.enabled"
          type="button"
          :disabled="twoFactor.isProcessing"
          class="rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
          @click="start2FASetup"
        >
          {{ twoFactor.isProcessing ? 'Memuat...' : 'Mulai Penyiapan 2FA' }}
        </button>
        <button
          v-else
          type="button"
          class="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-xs font-semibold text-red-600 hover:bg-red-100"
          @click="twoFactor.showDisableModal = true"
        >
          Nonaktifkan 2FA
        </button>
      </div>

      <!-- Disable Modal -->
      <div v-if="twoFactor.showDisableModal" class="mt-4 rounded-lg border border-red-100 bg-red-50/50 p-4">
        <p class="text-xs font-medium text-slate-700 mb-2">Masukkan password akun Anda untuk menonaktifkan 2FA:</p>
        <div class="flex gap-2 max-w-sm">
          <input
            v-model="twoFactor.disablePassword"
            type="password"
            placeholder="Password akun"
            class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs focus:border-red-500 focus:outline-none"
          />
          <button
            type="button"
            :disabled="twoFactor.isProcessing || !twoFactor.disablePassword"
            class="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
            @click="disable2FA"
          >
            Konfirmasi
          </button>
          <button
            type="button"
            class="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100"
            @click="twoFactor.showDisableModal = false; twoFactor.disablePassword = ''"
          >
            Batal
          </button>
        </div>
      </div>
    </div>

    <div v-if="auth.hasPermission('software.manage')" class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
      <h2 class="text-sm font-semibold text-slate-700">Software Whitelist</h2>
      <p class="mt-1 text-xs text-slate-400">
        Daftar software yang diizinkan terinstall. Kalau daftar ini kosong, sistem cuma memberi alert biasa
        (WARNING) setiap ada software baru. Begitu diisi minimal 1, software baru yang <strong>tidak</strong>
        ada di daftar ini akan memicu alert CRITICAL "TIDAK di whitelist" — sedangkan software yang memang ada
        di daftar tidak akan memicu alert sama sekali. Ini cuma memberi tahu, bukan mencegah instalasi.
      </p>

      <form class="mt-3 flex flex-wrap items-end gap-3" @submit.prevent="handleAddWhitelist">
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Nama Software</label>
          <input
            v-model="newWhitelistName"
            type="text"
            placeholder="mis. Google Chrome"
            class="w-64 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>
        <button
          type="submit"
          :disabled="isAddingWhitelist || !newWhitelistName.trim()"
          class="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {{ isAddingWhitelist ? 'Menambah...' : 'Tambah' }}
        </button>
      </form>
      <p v-if="whitelistError" class="mt-2 text-xs text-red-600">{{ whitelistError }}</p>

      <div v-if="isWhitelistLoading" class="mt-4 text-sm text-slate-400">Memuat...</div>
      <div v-else-if="whitelistEntries.length === 0" class="mt-4 text-sm text-slate-400">
        Belum ada software di whitelist — fitur ini masih nonaktif (semua software baru dapat alert WARNING biasa).
      </div>
      <ul v-else class="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-100">
        <li
          v-for="entry in whitelistEntries"
          :key="entry.id"
          class="flex items-center justify-between px-3 py-2 text-sm"
        >
          <div>
            <span class="text-slate-700">{{ entry.name }}</span>
            <span class="ml-2 text-xs text-slate-400">
              ditambahkan {{ entry.added_by || 'sistem' }} · {{ new Date(entry.created_at).toLocaleDateString() }}
            </span>
          </div>
          <button class="text-xs font-medium text-red-600 hover:underline" @click="handleRemoveWhitelist(entry)">
            Hapus
          </button>
        </li>
      </ul>
    </div>

    <StatusModal
      :open="status.open"
      :variant="status.variant"
      :title="status.title"
      :message="status.message"
      :auto-close-ms="2200"
      @primary="status.open = false"
      @close="status.open = false"
    />
  </div>
</template>
