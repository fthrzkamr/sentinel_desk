<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import LiveScreenPanel from '@/components/LiveScreenPanel.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import UsageBar from '@/components/UsageBar.vue'
import { listDevices } from '@/services/devices'
import { useAuthStore } from '@/stores/auth'
import { useMonitoringStore } from '@/stores/monitoring'
import { timeAgo } from '@/utils/time'

const router = useRouter()
const auth = useAuthStore()
const monitoring = useMonitoringStore()
const liveScreenDevice = ref(null)

const devices = ref([])
const isLoading = ref(true)
const errorMessage = ref('')
const search = ref('')

// Devices with the agent actually running send a fresh status on every metric
// cycle over the WebSocket — a device whose only status is what it was left
// at in the DB (never seen live) hasn't reported anything this session yet.
function liveFor(device) {
  return monitoring.liveDevices[device.device_id]
}

function displayStatus(device) {
  return liveFor(device)?.status || device.status
}

function usagePercent(device, key) {
  const value = liveFor(device)?.[key]
  return value === null || value === undefined ? null : value
}

function lastSeen(device) {
  return liveFor(device)?.last_seen || device.last_seen
}

const SEVERITY_ORDER = { CRITICAL: 0, WARNING: 1, ONLINE: 2, OFFLINE: 3, DISABLED: 4 }

const visibleDevices = computed(() => {
  const term = search.value.trim().toLowerCase()
  const filtered = term
    ? devices.value.filter(
        (d) =>
          d.device_id.toLowerCase().includes(term) ||
          d.hostname?.toLowerCase().includes(term) ||
          d.username?.toLowerCase().includes(term),
      )
    : devices.value

  return [...filtered].sort((a, b) => {
    const diff = (SEVERITY_ORDER[displayStatus(a)] ?? 9) - (SEVERITY_ORDER[displayStatus(b)] ?? 9)
    return diff !== 0 ? diff : a.device_id.localeCompare(b.device_id)
  })
})

async function fetchDevices() {
  try {
    const { data } = await listDevices({ page_size: 200 })
    devices.value = data.results
  } catch {
    errorMessage.value = 'Gagal memuat daftar device.'
  } finally {
    isLoading.value = false
  }
}

// Live metrics arrive over the WebSocket already connected at the layout
// level, but a device that just got enrolled/disabled elsewhere wouldn't
// show up here until the device list itself is re-fetched.
let refreshTimer = null

onMounted(() => {
  fetchDevices()
  refreshTimer = setInterval(fetchDevices, 30000)
})

onUnmounted(() => {
  clearInterval(refreshTimer)
})

function goToDetail(device) {
  router.push({ name: 'device-detail', params: { deviceId: device.device_id } })
}

function openLiveScreen(device) {
  liveScreenDevice.value = device
}

function closeLiveScreen() {
  liveScreenDevice.value = null
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold text-slate-800">Monitoring</h1>
        <p class="mt-1 text-xs text-slate-400">
          Semua device dengan agent terpasang, diurutkan yang paling butuh perhatian dulu. Update otomatis lewat
          WebSocket — halaman ini tidak perlu di-refresh manual.
        </p>
      </div>
      <input
        v-model="search"
        type="text"
        placeholder="Cari device ID, hostname, atau user..."
        class="w-64 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
      />
    </div>

    <div v-if="isLoading" class="rounded-xl bg-white p-10 text-center text-sm text-slate-400 shadow-sm ring-1 ring-slate-900/5">
      Memuat data...
    </div>
    <div v-else-if="errorMessage" class="rounded-xl bg-white p-10 text-center text-sm text-red-500 shadow-sm ring-1 ring-slate-900/5">
      {{ errorMessage }}
    </div>
    <div v-else-if="visibleDevices.length === 0" class="rounded-xl bg-white p-10 text-center text-sm text-slate-400 shadow-sm ring-1 ring-slate-900/5">
      {{ devices.length === 0 ? 'Belum ada device dengan agent terpasang.' : 'Tidak ada device yang cocok.' }}
    </div>

    <div v-else class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div
        v-for="device in visibleDevices"
        :key="device.id"
        class="cursor-pointer space-y-3 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-900/5 transition hover:ring-brand-300"
        @click="goToDetail(device)"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate font-mono text-xs text-slate-500">{{ device.device_id }}</p>
            <p class="truncate text-sm font-semibold text-slate-800">{{ device.hostname }}</p>
            <p class="truncate text-xs text-slate-500">
              {{ device.assigned_employee || 'Belum di-assign' }}
              <span v-if="device.branch"> · {{ device.branch }}</span>
            </p>
          </div>
          <StatusBadge :status="displayStatus(device)" />
        </div>

        <div class="space-y-2">
          <UsageBar label="CPU" :percent="usagePercent(device, 'cpu_percent')" />
          <UsageBar label="RAM" :percent="usagePercent(device, 'ram_percent')" />
          <UsageBar label="Disk" :percent="usagePercent(device, 'disk_percent')" />
        </div>

        <div class="flex items-center justify-between border-t border-slate-100 pt-2 text-xs text-slate-400">
          <span>{{ device.username || 'Tidak ada user login' }}</span>
          <span>{{ timeAgo(lastSeen(device)) }}</span>
        </div>

        <button
          v-if="auth.hasPermission('monitoring.live_screen')"
          class="w-full rounded-lg border border-slate-200 py-1.5 text-xs font-medium text-slate-600 hover:border-brand-300 hover:text-brand-700"
          @click.stop="openLiveScreen(device)"
        >
          Lihat Layar
        </button>
      </div>
    </div>

    <div
      v-if="liveScreenDevice"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4"
      @click.self="closeLiveScreen"
    >
      <div class="w-full max-w-2xl rounded-xl bg-white p-5 shadow-xl">
        <div class="mb-3 flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate text-sm font-semibold text-slate-800">
              {{ liveScreenDevice.hostname }}
              <span class="font-mono text-xs font-normal text-slate-400">({{ liveScreenDevice.device_id }})</span>
            </p>
            <p class="truncate text-xs text-slate-500">
              {{ liveScreenDevice.assigned_employee || 'Belum di-assign' }}
              <span v-if="liveScreenDevice.branch"> · {{ liveScreenDevice.branch }}</span>
            </p>
          </div>
          <button class="shrink-0 rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600" @click="closeLiveScreen">
            ✕
          </button>
        </div>
        <LiveScreenPanel :key="liveScreenDevice.device_id" :device-id="liveScreenDevice.device_id" />
      </div>
    </div>
  </div>
</template>
