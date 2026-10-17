<script setup>
import { onMounted, reactive, ref } from 'vue'

import StatusModal from '@/components/StatusModal.vue'
import { getSystemSettings, updateSystemSettings } from '@/services/settings'
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
  work_hours_start: null,
  work_hours_end: null,
})

const isLoading = ref(true)
const isSaving = ref(false)
const errorMessage = ref('')
const fieldErrors = ref({})
const updatedAt = ref(null)
const status = reactive({ open: false, variant: 'success', title: '', message: '' })

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
})

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
              Simpan App Usage/Browsing History/File Activity selama (hari)
            </label>
            <input v-model.number="form.activity_retention_days" type="number" min="1" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            <p v-if="fieldError('activity_retention_days')" class="mt-1 text-xs text-red-600">{{ fieldError('activity_retention_days') }}</p>
          </div>
        </div>
      </div>

      <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <h2 class="text-sm font-semibold text-slate-700">Jam Kerja</h2>
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
