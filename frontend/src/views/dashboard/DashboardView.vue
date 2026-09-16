<script setup>
import { computed, onMounted, ref } from 'vue'

import StatCard from '@/components/StatCard.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { listDevices } from '@/services/devices'
import { useAuthStore } from '@/stores/auth'
import { useMonitoringStore } from '@/stores/monitoring'
import { timeAgo } from '@/utils/time'

const auth = useAuthStore()
const monitoring = useMonitoringStore()

const devices = ref([])
const isLoading = ref(true)
const errorMessage = ref('')

async function fetchDevices() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = await listDevices({ page_size: 200 })
    devices.value = data.results
  } catch {
    errorMessage.value = 'Gagal memuat data device.'
  } finally {
    isLoading.value = false
  }
}

onMounted(fetchDevices)

function liveFor(device) {
  return monitoring.liveDevices[device.device_id]
}

const mergedDevices = computed(() =>
  devices.value.map((device) => ({
    ...device,
    status: liveFor(device)?.status || device.status,
    last_seen: liveFor(device)?.last_seen || device.last_seen,
  })),
)

const counts = computed(() => {
  const result = { total: mergedDevices.value.length, ONLINE: 0, OFFLINE: 0, WARNING: 0, CRITICAL: 0, DISABLED: 0 }
  for (const device of mergedDevices.value) {
    if (result[device.status] !== undefined) result[device.status] += 1
  }
  return result
})

const recentlyActive = computed(() =>
  [...mergedDevices.value]
    .filter((d) => d.last_seen)
    .sort((a, b) => new Date(b.last_seen) - new Date(a.last_seen))
    .slice(0, 5),
)

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 11) return 'Selamat pagi'
  if (hour < 15) return 'Selamat siang'
  if (hour < 19) return 'Selamat sore'
  return 'Selamat malam'
})
</script>

<template>
  <div class="space-y-6">
    <div class="relative overflow-hidden rounded-xl bg-gradient-to-br from-brand-600 to-brand-800 p-6 text-white shadow-sm">
      <div class="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10"></div>
      <div class="pointer-events-none absolute -bottom-16 right-24 h-32 w-32 rounded-full bg-white/10"></div>

      <div class="relative flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 class="text-xl font-semibold">{{ greeting }}, {{ auth.user?.username }}</h1>
          <p class="mt-1 max-w-xl text-sm text-brand-100">
            Ringkasan device secara realtime — status dan pemakaian CPU/RAM diperbarui otomatis
            lewat WebSocket tanpa perlu refresh halaman.
          </p>
        </div>
        <div class="flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-medium">
          <span
            class="h-2 w-2 rounded-full"
            :class="monitoring.connected ? 'bg-emerald-400 animate-pulse' : 'bg-slate-300'"
          ></span>
          {{ monitoring.connected ? 'Live terhubung' : 'Menghubungkan...' }}
        </div>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
      <StatCard label="Devices" :value="counts.total" color="blue">
        <template #icon>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-5 w-5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m-9 0h9m-9 0H4.5A2.25 2.25 0 012.25 15V5.25A2.25 2.25 0 014.5 3h15a2.25 2.25 0 012.25 2.25V15a2.25 2.25 0 01-2.25 2.25H15" />
          </svg>
        </template>
      </StatCard>

      <StatCard label="Online" :value="counts.ONLINE" color="emerald">
        <template #icon>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-5 w-5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8.288 15.038a5.25 5.25 0 017.424 0M5.106 11.856c3.807-3.808 9.98-3.808 13.788 0M1.924 8.674c5.565-5.565 14.587-5.565 20.152 0M12 20.25a.75.75 0 11-.001-1.501A.75.75 0 0112 20.25z" />
          </svg>
        </template>
      </StatCard>

      <StatCard label="Offline" :value="counts.OFFLINE" color="slate">
        <template #icon>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-5 w-5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3 3l18 18M8.288 15.038a5.25 5.25 0 017.424 0M12 20.25a.75.75 0 11-.001-1.501A.75.75 0 0112 20.25z" />
          </svg>
        </template>
      </StatCard>

      <StatCard label="Warning" :value="counts.WARNING" color="amber">
        <template #icon>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-5 w-5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
        </template>
      </StatCard>

      <StatCard label="Critical" :value="counts.CRITICAL" color="red">
        <template #icon>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-5 w-5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m0 3.75h.007v.008H12v-.008zM21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </template>
      </StatCard>

    </div>

    <div class="rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
      <div class="flex items-center justify-between border-b border-slate-100 px-5 py-4">
        <h2 class="text-sm font-semibold text-slate-700">Device Paling Baru Aktif</h2>
        <RouterLink to="/devices" class="text-xs font-medium text-brand-600 hover:underline">Lihat semua →</RouterLink>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-slate-100 text-sm">
          <thead class="text-left text-xs font-medium uppercase tracking-wide text-slate-500">
            <tr>
              <th class="px-5 py-2.5">Device ID</th>
              <th class="px-5 py-2.5">Hostname</th>
              <th class="px-5 py-2.5">Karyawan</th>
              <th class="px-5 py-2.5">Cabang</th>
              <th class="px-5 py-2.5">Status</th>
              <th class="px-5 py-2.5">Last Seen</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-if="isLoading">
              <td colspan="6" class="px-5 py-10 text-center text-slate-400">Memuat data...</td>
            </tr>
            <tr v-else-if="errorMessage">
              <td colspan="6" class="px-5 py-10 text-center text-red-500">{{ errorMessage }}</td>
            </tr>
            <tr v-else-if="recentlyActive.length === 0">
              <td colspan="6" class="px-5 py-10 text-center">
                <div class="flex flex-col items-center gap-2 text-slate-400">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-10 w-10 text-slate-300">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m-9 0h9m-9 0H4.5A2.25 2.25 0 012.25 15V5.25A2.25 2.25 0 014.5 3h15a2.25 2.25 0 012.25 2.25V15a2.25 2.25 0 01-2.25 2.25H15" />
                  </svg>
                  <span>Belum ada device yang aktif.</span>
                  <RouterLink to="/agents" class="text-xs font-medium text-brand-600 hover:underline">
                    Buat enrollment token →
                  </RouterLink>
                </div>
              </td>
            </tr>
            <tr v-for="device in recentlyActive" v-else :key="device.id" class="hover:bg-slate-50">
              <td class="px-5 py-3 font-mono text-xs text-slate-600">{{ device.device_id }}</td>
              <td class="px-5 py-3">{{ device.hostname }}</td>
              <td class="px-5 py-3">{{ device.assigned_employee || '-' }}</td>
              <td class="px-5 py-3">{{ device.branch || '-' }}</td>
              <td class="px-5 py-3"><StatusBadge :status="device.status" /></td>
              <td class="px-5 py-3 text-slate-500">{{ timeAgo(device.last_seen) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
