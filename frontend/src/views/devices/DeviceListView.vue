<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import ConfirmDialog from '@/components/ConfirmDialog.vue'
import NavIcon from '@/components/NavIcon.vue'
import Pagination from '@/components/Pagination.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import api from '@/services/api'
import {
  approveDevice,
  disableDevice,
  enableDevice,
  getDeviceAssetSuggestions,
  linkAsset,
  listDevices,
  updateDeviceOrgAssignment,
} from '@/services/devices'
import { listEmployees } from '@/services/organization'
import { useAuthStore } from '@/stores/auth'
import { useMonitoringStore } from '@/stores/monitoring'
import { timeAgo } from '@/utils/time'

const PAGE_SIZE = 25

const router = useRouter()
const auth = useAuthStore()
const monitoring = useMonitoringStore()

function liveFor(device) {
  return monitoring.liveDevices[device.device_id]
}

function displayStatus(device) {
  return liveFor(device)?.status || device.status
}

function usagePercent(device, key) {
  const value = liveFor(device)?.[key]
  return value === null || value === undefined ? null : Math.round(value)
}

function lastSeen(device) {
  return liveFor(device)?.last_seen || device.last_seen
}

const devices = ref([])
const isLoading = ref(true)
const errorMessage = ref('')
const search = ref('')
const statusFilter = ref('')
const pageCount = ref(0)
const currentUrl = ref(null)
const nextUrl = ref(null)
const previousUrl = ref(null)
const pageOffset = ref(0)
const offsetStack = [0]
const currentPage = computed(() => Math.floor(pageOffset.value / PAGE_SIZE) + 1)

const confirmState = reactive({ open: false, device: null, action: null })
const pendingDevicesCount = computed(() => devices.value.filter((d) => !d.is_approved).length)

const statusOptions = ['', 'ONLINE', 'OFFLINE', 'WARNING', 'CRITICAL', 'DISABLED']

async function fetchDevices(url = null) {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = url
      ? await api.get(url, { baseURL: '' })
      : await listDevices({ search: search.value || undefined, status: statusFilter.value || undefined })

    devices.value = data.results
    pageCount.value = data.count
    nextUrl.value = data.next
    previousUrl.value = data.previous
    currentUrl.value = url
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || 'Gagal memuat daftar device.'
  } finally {
    isLoading.value = false
  }
}

let searchDebounce = null
watch([search, statusFilter], () => {
  clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => {
    offsetStack.length = 1
    offsetStack[0] = 0
    pageOffset.value = 0
    fetchDevices()
  }, 300)
})

onMounted(fetchDevices)

function goNext() {
  offsetStack.push(pageOffset.value + devices.value.length)
  pageOffset.value = offsetStack[offsetStack.length - 1]
  fetchDevices(nextUrl.value)
}

function goPrevious() {
  if (offsetStack.length > 1) offsetStack.pop()
  pageOffset.value = offsetStack[offsetStack.length - 1]
  fetchDevices(previousUrl.value)
}

function goToDetail(device) {
  router.push({ name: 'device-detail', params: { deviceId: device.device_id } })
}

function askToggleStatus(device) {
  confirmState.open = true
  confirmState.device = device
  confirmState.action = device.status === 'DISABLED' ? 'enable' : 'disable'
}

async function confirmToggle() {
  const { device, action } = confirmState
  confirmState.open = false
  try {
    if (action === 'disable') {
      await disableDevice(device.device_id)
    } else {
      await enableDevice(device.device_id)
    }
    await fetchDevices(currentUrl.value)
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || 'Aksi gagal dilakukan.'
  }
}

// Approving is non-destructive (opposite of disable) so it skips the
// confirm dialog — same reasoning as "Aktifkan" for agent releases.
async function handleApprove(device) {
  try {
    await approveDevice(device.device_id)
    await fetchDevices(currentUrl.value)
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || 'Gagal approve device.'
  }
}

// --- Quick "Ganti Pengguna" (reassign employee without opening Device
// Detail) — all 171 employees are loaded once and filtered client-side;
// there's no search param on the employees endpoint and this dataset is
// small enough that a server round-trip per keystroke isn't worth it. ---

const reassignState = reactive({ open: false, device: null, search: '', selectedId: '', isSaving: false, error: '' })
const allEmployees = ref([])
const employeesLoaded = ref(false)

const filteredEmployees = computed(() => {
  const q = reassignState.search.trim().toLowerCase()
  if (!q) return allEmployees.value
  return allEmployees.value.filter((e) => e.full_name.toLowerCase().includes(q))
})

// --- Spec-based asset suggestions (for a device nobody has assigned an
// employee to yet, so there's no name to search against at all) ---
const assetSuggestions = ref([])
const isLoadingSuggestions = ref(false)
const isPickingSuggestion = ref(false)

async function askReassign(device) {
  reassignState.open = true
  reassignState.device = device
  // No pre-selection: the list's own assigned_employee field is a plain
  // display string (StringRelatedField), not an id, so there's nothing to
  // preselect against — the modal's header shows the current name instead.
  reassignState.search = ''
  reassignState.selectedId = ''
  reassignState.error = ''
  assetSuggestions.value = []
  if (!employeesLoaded.value) {
    const { data } = await listEmployees({ page_size: 500 })
    allEmployees.value = data.results ?? data
    employeesLoaded.value = true
  }
  if (!device.assigned_employee) {
    isLoadingSuggestions.value = true
    try {
      const { data } = await getDeviceAssetSuggestions(device.device_id)
      assetSuggestions.value = data
    } catch {
      assetSuggestions.value = []
    } finally {
      isLoadingSuggestions.value = false
    }
  }
}

async function pickSuggestion(asset) {
  isPickingSuggestion.value = true
  reassignState.error = ''
  try {
    await linkAsset(asset.id, reassignState.device.device_id)
    reassignState.open = false
    await fetchDevices(currentUrl.value)
  } catch (error) {
    reassignState.error = error.response?.data?.detail || 'Gagal menautkan asset.'
  } finally {
    isPickingSuggestion.value = false
  }
}

async function confirmReassign() {
  reassignState.isSaving = true
  reassignState.error = ''
  try {
    await updateDeviceOrgAssignment(reassignState.device.device_id, {
      assigned_employee: reassignState.selectedId || null,
    })
    reassignState.open = false
    await fetchDevices(currentUrl.value)
  } catch (error) {
    reassignState.error = error.response?.data?.detail || 'Gagal mengganti pengguna.'
  } finally {
    reassignState.isSaving = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <!-- Banner Perangkat Menunggu Approval -->
    <div
      v-if="pendingDevicesCount > 0"
      class="flex items-center justify-between rounded-xl bg-amber-50 p-4 border border-amber-200"
    >
      <div class="flex items-center gap-3">
        <div class="flex h-9 w-9 items-center justify-center rounded-full bg-amber-100 text-amber-600">
          <NavIcon name="bell" class="h-5 w-5" />
        </div>
        <div>
          <h4 class="text-sm font-semibold text-amber-900">
            {{ pendingDevicesCount }} Perangkat Baru Menunggu Persetujuan
          </h4>
          <p class="text-xs text-amber-700">
            Laptop baru yang baru saja menginstall agent terdaftar otomatis. Klik tombol check di kolom aksi untuk menyetujui (Approve).
          </p>
        </div>
      </div>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-slate-800">Devices</h1>
      <div class="flex flex-wrap gap-2">
        <input
          v-model="search"
          type="text"
          placeholder="Cari device ID, hostname, user, atau asset code..."
          class="w-64 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <select
          v-model="statusFilter"
          class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option v-for="option in statusOptions" :key="option" :value="option">
            {{ option || 'Semua Status' }}
          </option>
        </select>
      </div>
    </div>

    <div class="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
      <table class="w-full min-w-[900px] table-fixed divide-y divide-slate-200 text-sm">
        <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th class="w-[3%] px-4 py-2.5">No</th>
            <th class="w-[13%] px-4 py-2.5">Kode Asset</th>
            <th class="w-[9%] px-4 py-2.5">Model</th>
            <th class="w-[9%] px-4 py-2.5">Cabang</th>
            <th class="w-[14%] px-4 py-2.5">Karyawan</th>
            <th class="w-[6%] px-4 py-2.5">CPU</th>
            <th class="w-[7%] px-4 py-2.5">RAM</th>
            <th class="w-[7%] px-4 py-2.5">Disk</th>
            <th class="w-[10%] px-4 py-2.5">Status</th>
            <th class="w-[7%] px-4 py-2.5">Last Seen</th>
            <th class="w-[15%] px-4 py-2.5 text-right">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100" :class="{ 'opacity-50 transition-opacity': isLoading && devices.length > 0 }">
          <tr v-if="isLoading && devices.length === 0">
            <td colspan="11" class="px-4 py-8 text-center text-slate-400">Memuat data...</td>
          </tr>
          <tr v-else-if="errorMessage">
            <td colspan="11" class="px-4 py-8 text-center text-red-500">{{ errorMessage }}</td>
          </tr>
          <tr v-else-if="devices.length === 0">
            <td colspan="11" class="px-4 py-8 text-center text-slate-400">
              Belum ada device terdaftar. Buat enrollment token di menu Agents lalu jalankan agent.
            </td>
          </tr>
          <tr v-for="(device, index) in devices" v-else :key="device.id" class="hover:bg-slate-50">
            <td class="px-4 py-2.5 text-slate-500">{{ pageOffset + index + 1 }}</td>
            <td class="break-words px-4 py-2.5">
              <div v-if="device.asset" class="font-mono text-xs font-medium text-slate-700">{{ device.asset.asset_code }}</div>
              <div :class="device.asset ? 'text-xs text-slate-400' : ''">{{ device.hostname }}</div>
            </td>
            <td class="break-words px-4 py-2.5">{{ device.system_family || '-' }}</td>
            <td class="break-words px-4 py-2.5">{{ device.branch_name || '-' }}</td>
            <td class="break-words px-4 py-2.5">{{ device.assigned_employee || '-' }}</td>
            <td class="px-4 py-2.5 font-medium text-slate-700">
              {{ usagePercent(device, 'cpu_percent') !== null ? `${usagePercent(device, 'cpu_percent')}%` : '-' }}
            </td>
            <td class="break-words px-4 py-2.5">
              <div v-if="usagePercent(device, 'ram_percent') !== null" class="font-medium text-slate-700">
                {{ usagePercent(device, 'ram_percent') }}%
              </div>
              <div class="text-xs text-slate-400">{{ device.ram || '-' }}</div>
            </td>
            <td class="break-words px-4 py-2.5">
              <div v-if="usagePercent(device, 'disk_percent') !== null" class="font-medium text-slate-700">
                {{ usagePercent(device, 'disk_percent') }}%
              </div>
              <div class="text-xs text-slate-400">{{ device.disk || '-' }}</div>
            </td>
            <td class="whitespace-nowrap px-4 py-2.5">
              <div class="flex flex-col items-start gap-1">
                <StatusBadge :status="displayStatus(device)" />
                <span
                  v-if="!device.is_approved"
                  class="inline-block rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-700"
                  title="Device ini enroll lewat reusable deployment key — belum bisa mengirim data sampai di-approve"
                >
                  Pending
                </span>
              </div>
            </td>
            <td class="whitespace-nowrap px-4 py-2.5 text-slate-500">{{ timeAgo(lastSeen(device)) }}</td>
            <td class="whitespace-nowrap px-4 py-2.5 text-right">
              <div class="flex flex-nowrap justify-end gap-1">
                <button
                  class="shrink-0 rounded-md border border-slate-300 p-1 text-slate-600 hover:bg-slate-50"
                  title="View"
                  @click="goToDetail(device)"
                >
                  <NavIcon name="eye" class="h-3.5 w-3.5" />
                </button>
                <button
                  v-if="auth.hasPermission('device.manage')"
                  class="shrink-0 rounded-md border border-slate-300 p-1 text-slate-600 hover:bg-slate-50"
                  title="Ganti Pengguna"
                  @click="askReassign(device)"
                >
                  <NavIcon name="users" class="h-3.5 w-3.5" />
                </button>
                <button
                  v-if="!device.is_approved && auth.hasPermission('device.disable')"
                  class="shrink-0 rounded-md bg-amber-600 p-1 text-white hover:bg-amber-700"
                  title="Approve"
                  @click="handleApprove(device)"
                >
                  <NavIcon name="check" class="h-3.5 w-3.5" />
                </button>
                <button
                  v-if="auth.hasPermission('device.disable')"
                  class="shrink-0 rounded-md p-1 text-white"
                  :class="displayStatus(device) === 'DISABLED' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-red-600 hover:bg-red-700'"
                  :title="displayStatus(device) === 'DISABLED' ? 'Enable' : 'Disable'"
                  @click="askToggleStatus(device)"
                >
                  <NavIcon name="power" class="h-3.5 w-3.5" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <Pagination
      v-if="devices.length > 0"
      :page="currentPage"
      :page-size="PAGE_SIZE"
      :count="pageCount"
      :has-previous="Boolean(previousUrl)"
      :has-next="Boolean(nextUrl)"
      @previous="goPrevious"
      @next="goNext"
    />

    <ConfirmDialog
      :open="confirmState.open"
      :title="confirmState.action === 'disable' ? 'Nonaktifkan device?' : 'Aktifkan kembali device?'"
      :message="`${confirmState.device?.asset ? confirmState.device.asset.asset_code : confirmState.device?.hostname} akan di-${confirmState.action === 'disable' ? 'nonaktifkan — agent tidak bisa mengirim heartbeat lagi' : 'aktifkan kembali'}.`"
      :confirm-label="confirmState.action === 'disable' ? 'Disable' : 'Enable'"
      :danger="confirmState.action === 'disable'"
      @confirm="confirmToggle"
      @cancel="confirmState.open = false"
    />

    <div
      v-if="reassignState.open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      @click.self="reassignState.open = false"
    >
      <div class="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
        <h2 class="text-base font-semibold text-slate-800">Ganti Pengguna</h2>
        <p class="mt-1 text-sm text-slate-500">
          {{ reassignState.device?.asset ? reassignState.device.asset.asset_code : reassignState.device?.hostname }}
          — pengguna saat ini: <strong>{{ reassignState.device?.assigned_employee || 'Belum diatur' }}</strong>
        </p>

        <div v-if="isLoadingSuggestions" class="mt-3 text-xs text-slate-400">Mencari saran berdasarkan spesifikasi...</div>
        <div v-else-if="assetSuggestions.length > 0" class="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2.5">
          <p class="text-xs font-medium text-amber-800">
            Saran berdasarkan spesifikasi laptop ({{ reassignState.device?.model || reassignState.device?.hostname }}) —
            belum tentu benar, silakan pilih yang paling cocok:
          </p>
          <div class="mt-1.5 max-h-40 space-y-1 overflow-y-auto">
            <button
              v-for="suggestion in assetSuggestions"
              :key="suggestion.id"
              type="button"
              :disabled="isPickingSuggestion"
              class="block w-full rounded-md bg-white px-2.5 py-1.5 text-left text-xs hover:bg-amber-100 disabled:opacity-60"
              @click="pickSuggestion(suggestion)"
            >
              <span class="font-mono font-medium text-slate-700">{{ suggestion.asset_code }}</span>
              <span class="text-slate-500"> — {{ suggestion.raw_penanggung_jawab || '-' }}</span>
              <span class="text-slate-400"> ({{ suggestion.nama_aset }})</span>
            </button>
          </div>
        </div>

        <input
          v-model="reassignState.search"
          type="text"
          placeholder="Cari nama karyawan..."
          class="mt-3 w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <div class="mt-2 max-h-56 overflow-y-auto rounded-lg border border-slate-100">
          <button
            type="button"
            class="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
            :class="reassignState.selectedId === '' ? 'bg-brand-50 font-medium text-brand-700' : 'text-slate-500'"
            @click="reassignState.selectedId = ''"
          >
            Kosongkan (tidak ada pengguna)
          </button>
          <button
            v-for="employee in filteredEmployees"
            :key="employee.id"
            type="button"
            class="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
            :class="reassignState.selectedId === employee.id ? 'bg-brand-50 font-medium text-brand-700' : 'text-slate-700'"
            @click="reassignState.selectedId = employee.id"
          >
            {{ employee.full_name }}
            <span class="text-xs text-slate-400">{{ employee.department_label || '' }}</span>
          </button>
          <p v-if="filteredEmployees.length === 0" class="px-3 py-4 text-center text-sm text-slate-400">
            Tidak ada karyawan yang cocok.
          </p>
        </div>

        <p v-if="reassignState.error" class="mt-2 text-xs text-red-600">{{ reassignState.error }}</p>

        <div class="mt-4 flex justify-end gap-2">
          <button
            class="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            @click="reassignState.open = false"
          >
            Batal
          </button>
          <button
            :disabled="reassignState.isSaving"
            class="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
            @click="confirmReassign"
          >
            {{ reassignState.isSaving ? 'Menyimpan...' : 'Simpan' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
