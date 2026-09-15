<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import ConfirmDialog from '@/components/ConfirmDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import api from '@/services/api'
import { disableDevice, enableDevice, listDevices } from '@/services/devices'
import { useAuthStore } from '@/stores/auth'
import { useMonitoringStore } from '@/stores/monitoring'
import { timeAgo } from '@/utils/time'

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

const confirmState = reactive({ open: false, device: null, action: null })

const statusOptions = ['', 'ONLINE', 'OFFLINE', 'WARNING', 'CRITICAL', 'DISABLED']

async function fetchDevices(url = null) {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = url
      ? await api.get(url)
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
  searchDebounce = setTimeout(() => fetchDevices(), 300)
})

onMounted(fetchDevices)

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
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-slate-800">Devices</h1>
      <div class="flex flex-wrap gap-2">
        <input
          v-model="search"
          type="text"
          placeholder="Cari device ID, hostname, atau user..."
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
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th class="px-4 py-3">Device ID</th>
            <th class="px-4 py-3">Hostname</th>
            <th class="px-4 py-3">User</th>
            <th class="px-4 py-3">IP</th>
            <th class="px-4 py-3">CPU</th>
            <th class="px-4 py-3">RAM</th>
            <th class="px-4 py-3">Disk</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Last Seen</th>
            <th class="px-4 py-3 text-right">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-if="isLoading">
            <td colspan="10" class="px-4 py-8 text-center text-slate-400">Memuat data...</td>
          </tr>
          <tr v-else-if="errorMessage">
            <td colspan="10" class="px-4 py-8 text-center text-red-500">{{ errorMessage }}</td>
          </tr>
          <tr v-else-if="devices.length === 0">
            <td colspan="10" class="px-4 py-8 text-center text-slate-400">
              Belum ada device terdaftar. Buat enrollment token di menu Agents lalu jalankan agent.
            </td>
          </tr>
          <tr v-for="device in devices" v-else :key="device.id" class="hover:bg-slate-50">
            <td class="px-4 py-3 font-mono text-xs text-slate-700">{{ device.device_id }}</td>
            <td class="px-4 py-3">{{ device.hostname }}</td>
            <td class="px-4 py-3">{{ device.username || '-' }}</td>
            <td class="px-4 py-3">{{ device.ip_address || '-' }}</td>
            <td class="px-4 py-3">
              <div v-if="usagePercent(device, 'cpu_percent') !== null" class="font-medium text-slate-700">
                {{ usagePercent(device, 'cpu_percent') }}%
              </div>
              <div class="text-xs text-slate-400">{{ device.cpu || '-' }}</div>
            </td>
            <td class="px-4 py-3">
              <div v-if="usagePercent(device, 'ram_percent') !== null" class="font-medium text-slate-700">
                {{ usagePercent(device, 'ram_percent') }}%
              </div>
              <div class="text-xs text-slate-400">{{ device.ram || '-' }}</div>
            </td>
            <td class="px-4 py-3">
              <div v-if="usagePercent(device, 'disk_percent') !== null" class="font-medium text-slate-700">
                {{ usagePercent(device, 'disk_percent') }}%
              </div>
              <div class="text-xs text-slate-400">{{ device.disk || '-' }}</div>
            </td>
            <td class="px-4 py-3"><StatusBadge :status="displayStatus(device)" /></td>
            <td class="px-4 py-3 text-slate-500">{{ timeAgo(lastSeen(device)) }}</td>
            <td class="px-4 py-3 text-right">
              <div class="flex justify-end gap-2">
                <button class="text-brand-600 hover:underline" @click="goToDetail(device)">View</button>
                <button
                  v-if="auth.hasPermission('device.disable')"
                  class="hover:underline"
                  :class="displayStatus(device) === 'DISABLED' ? 'text-emerald-600' : 'text-red-600'"
                  @click="askToggleStatus(device)"
                >
                  {{ displayStatus(device) === 'DISABLED' ? 'Enable' : 'Disable' }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="!isLoading && devices.length > 0" class="flex items-center justify-between text-sm text-slate-500">
      <span>{{ pageCount }} device total</span>
      <div class="flex gap-2">
        <button
          class="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
          :disabled="!previousUrl"
          @click="fetchDevices(previousUrl)"
        >
          Previous
        </button>
        <button
          class="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
          :disabled="!nextUrl"
          @click="fetchDevices(nextUrl)"
        >
          Next
        </button>
      </div>
    </div>

    <ConfirmDialog
      :open="confirmState.open"
      :title="confirmState.action === 'disable' ? 'Nonaktifkan device?' : 'Aktifkan kembali device?'"
      :message="`${confirmState.device?.device_id} (${confirmState.device?.hostname}) akan di-${confirmState.action === 'disable' ? 'nonaktifkan — agent tidak bisa mengirim heartbeat lagi' : 'aktifkan kembali'}.`"
      :confirm-label="confirmState.action === 'disable' ? 'Disable' : 'Enable'"
      :danger="confirmState.action === 'disable'"
      @confirm="confirmToggle"
      @cancel="confirmState.open = false"
    />
  </div>
</template>
