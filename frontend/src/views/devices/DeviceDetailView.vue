<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ConfirmDialog from '@/components/ConfirmDialog.vue'
import LeafletMap from '@/components/LeafletMap.vue'
import LiveScreenPanel from '@/components/LiveScreenPanel.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import UsageBar from '@/components/UsageBar.vue'
import { disableDevice, enableDevice, getDevice } from '@/services/devices'
import { getDeviceLocationHistory } from '@/services/locations'
import { getLatestMetric } from '@/services/monitoring'
import { listSoftware } from '@/services/software'
import { useAuthStore } from '@/stores/auth'
import { useMonitoringStore } from '@/stores/monitoring'
import { downloadCsv } from '@/utils/csv'
import { timeAgo } from '@/utils/time'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const monitoring = useMonitoringStore()

const device = ref(null)
const latestMetric = ref(null)
const isLoading = ref(true)
const errorMessage = ref('')
const activeTab = ref('overview')
const confirmOpen = ref(false)

const tabs = computed(() => [
  { key: 'overview', label: 'Overview', available: true },
  { key: 'metrics', label: 'Metrics', available: true },
  { key: 'hardware', label: 'Hardware', available: true },
  { key: 'software', label: 'Software', available: true },
  { key: 'location', label: 'Location', available: true },
  { key: 'live-screen', label: 'Live Screen', available: auth.hasPermission('monitoring.live_screen') },
  { key: 'history', label: 'History', available: false },
  { key: 'audit', label: 'Audit', available: false },
])

const liveMetric = computed(() => monitoring.liveDevices[route.params.deviceId])

const displayStatus = computed(() => liveMetric.value?.status || device.value?.status)
const displayLastSeen = computed(() => liveMetric.value?.last_seen || device.value?.last_seen)

const metric = computed(() => ({
  cpu_percent: liveMetric.value?.cpu_percent ?? latestMetric.value?.cpu_percent ?? null,
  ram_percent: liveMetric.value?.ram_percent ?? latestMetric.value?.ram_percent ?? null,
  disk_percent: liveMetric.value?.disk_percent ?? latestMetric.value?.disk_percent ?? null,
  battery_percent: liveMetric.value?.battery_percent ?? latestMetric.value?.battery_percent ?? null,
  battery_charging: liveMetric.value?.battery_charging ?? latestMetric.value?.battery_charging ?? null,
  net_upload_kbps: latestMetric.value?.net_upload_kbps ?? null,
  net_download_kbps: latestMetric.value?.net_download_kbps ?? null,
  uptime_seconds: latestMetric.value?.uptime_seconds ?? null,
  recorded_at: latestMetric.value?.recorded_at ?? null,
}))

const toggleAction = computed(() => (displayStatus.value === 'DISABLED' ? 'enable' : 'disable'))

function formatUptime(seconds) {
  if (seconds === null || seconds === undefined) return 'Not Available'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

async function fetchDevice() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = await getDevice(route.params.deviceId)
    device.value = data
  } catch (error) {
    errorMessage.value =
      error.response?.status === 404 ? 'Device tidak ditemukan.' : 'Gagal memuat detail device.'
  } finally {
    isLoading.value = false
  }
}

async function fetchLatestMetric() {
  try {
    const { data } = await getLatestMetric(route.params.deviceId)
    latestMetric.value = data
  } catch {
    latestMetric.value = null
  }
}

const softwareList = ref([])
const isSoftwareLoading = ref(false)
const softwareSearch = ref('')
const softwareLoaded = ref(false)

async function fetchSoftware() {
  isSoftwareLoading.value = true
  try {
    const { data } = await listSoftware({
      device: route.params.deviceId,
      search: softwareSearch.value || undefined,
      ordering: 'name',
      page_size: 500,
    })
    softwareList.value = data.results
    softwareLoaded.value = true
  } catch {
    softwareList.value = []
  } finally {
    isSoftwareLoading.value = false
  }
}

let softwareSearchDebounce = null
watch(softwareSearch, () => {
  clearTimeout(softwareSearchDebounce)
  softwareSearchDebounce = setTimeout(fetchSoftware, 300)
})

function exportSoftwareCsv() {
  downloadCsv(`software-${device.value.device_id}.csv`, softwareList.value, [
    { key: 'name', label: 'Software' },
    { key: 'version', label: 'Versi' },
    { key: 'publisher', label: 'Publisher' },
    { key: 'install_date', label: 'Tanggal Install' },
  ])
}

const locationHistory = ref([])
const isLocationLoading = ref(false)
const locationLoaded = ref(false)

async function fetchLocationHistory() {
  isLocationLoading.value = true
  try {
    const { data } = await getDeviceLocationHistory(route.params.deviceId, { page_size: 50 })
    locationHistory.value = data.results
    locationLoaded.value = true
  } catch {
    locationHistory.value = []
  } finally {
    isLocationLoading.value = false
  }
}

const currentLocation = computed(() => locationHistory.value[0] || null)
const locationMarkers = computed(() =>
  currentLocation.value && currentLocation.value.latitude !== null
    ? [
        {
          lat: currentLocation.value.latitude,
          lng: currentLocation.value.longitude,
          accuracy: currentLocation.value.accuracy_meters,
          popupHtml: `<strong>${device.value.device_id}</strong><br>${device.value.hostname}`,
        },
      ]
    : [],
)

watch(activeTab, (tab) => {
  if (tab === 'software' && !softwareLoaded.value) fetchSoftware()
  if (tab === 'location' && !locationLoaded.value) fetchLocationHistory()
})

onMounted(() => {
  fetchDevice()
  fetchLatestMetric()
})

async function confirmToggle() {
  confirmOpen.value = false
  try {
    if (toggleAction.value === 'disable') {
      await disableDevice(device.value.device_id)
    } else {
      await enableDevice(device.value.device_id)
    }
    await fetchDevice()
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || 'Aksi gagal dilakukan.'
  }
}
</script>

<template>
  <div class="space-y-4">
    <button class="text-sm text-brand-600 hover:underline" @click="router.push({ name: 'devices' })">
      &larr; Kembali ke daftar Devices
    </button>

    <div v-if="isLoading" class="rounded-xl bg-white p-6 text-center text-slate-400 shadow-sm ring-1 ring-slate-900/5">
      Memuat data...
    </div>

    <div v-else-if="errorMessage" class="rounded-xl bg-white p-6 text-center text-red-500 shadow-sm ring-1 ring-slate-900/5">
      {{ errorMessage }}
    </div>

    <template v-else-if="device">
      <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <div>
          <div class="flex items-center gap-3">
            <h1 class="text-lg font-semibold text-slate-800">{{ device.device_id }}</h1>
            <StatusBadge :status="displayStatus" />
          </div>
          <p class="mt-1 text-sm text-slate-500">
            {{ device.hostname }} &middot; {{ device.username || 'Tidak ada user login' }}
          </p>
        </div>
        <button
          v-if="auth.hasPermission('device.disable')"
          class="rounded-md px-3 py-1.5 text-sm font-medium text-white"
          :class="toggleAction === 'disable' ? 'bg-red-600 hover:bg-red-700' : 'bg-emerald-600 hover:bg-emerald-700'"
          @click="confirmOpen = true"
        >
          {{ toggleAction === 'disable' ? 'Disable Device' : 'Enable Device' }}
        </button>
      </div>

      <div class="rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
        <div class="flex flex-wrap border-b border-slate-200 px-2">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="border-b-2 px-4 py-3 text-sm font-medium"
            :class="[
              activeTab === tab.key ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500 hover:text-slate-700',
              !tab.available && 'cursor-not-allowed text-slate-300 hover:text-slate-300',
            ]"
            :disabled="!tab.available"
            @click="tab.available && (activeTab = tab.key)"
          >
            {{ tab.label }}
          </button>
        </div>

        <div class="p-6">
          <div v-if="activeTab === 'overview'" class="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
            <div><dt class="text-xs uppercase text-slate-400">Hostname</dt><dd>{{ device.hostname }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Computer Name</dt><dd>{{ device.computer_name || '-' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Logged-in User</dt><dd>{{ device.username || '-' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">IP Address</dt><dd>{{ device.ip_address || '-' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">MAC Address</dt><dd>{{ device.mac_address || '-' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Agent Version</dt><dd>{{ device.agent_version || '-' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">First Registered</dt><dd>{{ new Date(device.first_registered).toLocaleString() }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Last Seen</dt><dd>{{ timeAgo(displayLastSeen) }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Company</dt><dd>{{ device.company || 'Belum diatur' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Branch</dt><dd>{{ device.branch || 'Belum diatur' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Department</dt><dd>{{ device.department || 'Belum diatur' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Assigned Employee</dt><dd>{{ device.assigned_employee || 'Belum diatur' }}</dd></div>
          </div>

          <div v-else-if="activeTab === 'hardware'" class="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
            <div><dt class="text-xs uppercase text-slate-400">OS</dt><dd>{{ device.os_name || '-' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">OS Version</dt><dd>{{ device.os_version || '-' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Architecture</dt><dd>{{ device.architecture || '-' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">CPU</dt><dd>{{ device.cpu || '-' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">RAM</dt><dd>{{ device.ram || '-' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Disk</dt><dd>{{ device.disk || '-' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Manufacturer</dt><dd>{{ device.manufacturer || 'Not Available' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Model</dt><dd>{{ device.model || 'Not Available' }}</dd></div>
            <div><dt class="text-xs uppercase text-slate-400">Serial Number</dt><dd>{{ device.serial_number || 'Not Available' }}</dd></div>
            <p class="col-span-full mt-2 text-xs text-slate-400">
              Pemakaian CPU/RAM/Disk secara realtime ada di tab Metrics.
            </p>
          </div>

          <div v-else-if="activeTab === 'metrics'" class="space-y-6">
            <div v-if="!metric.recorded_at && !liveMetric" class="py-10 text-center text-sm text-slate-400">
              Belum ada data metrics dari device ini. Pastikan agent sudah berjalan.
            </div>
            <template v-else>
              <div class="grid grid-cols-1 gap-6 sm:grid-cols-3">
                <UsageBar label="CPU" :percent="metric.cpu_percent" />
                <UsageBar label="RAM" :percent="metric.ram_percent" />
                <UsageBar label="Disk" :percent="metric.disk_percent" />
              </div>

              <div class="grid grid-cols-1 gap-x-8 gap-y-4 border-t border-slate-100 pt-5 sm:grid-cols-3">
                <div>
                  <dt class="text-xs uppercase text-slate-400">Battery</dt>
                  <dd>
                    {{ metric.battery_percent === null ? 'Not Available' : `${Math.round(metric.battery_percent)}%` }}
                    <span v-if="metric.battery_charging" class="text-xs text-emerald-600">(Charging)</span>
                  </dd>
                </div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Network Upload</dt>
                  <dd>{{ metric.net_upload_kbps === null ? 'Not Available' : `${Math.round(metric.net_upload_kbps)} kbps` }}</dd>
                </div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Network Download</dt>
                  <dd>{{ metric.net_download_kbps === null ? 'Not Available' : `${Math.round(metric.net_download_kbps)} kbps` }}</dd>
                </div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Uptime</dt>
                  <dd>{{ formatUptime(metric.uptime_seconds) }}</dd>
                </div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Sampel Terakhir</dt>
                  <dd>{{ metric.recorded_at ? timeAgo(metric.recorded_at) : 'Live' }}</dd>
                </div>
              </div>
              <p class="text-xs text-slate-400">
                Grafik tren historis CPU/RAM/Disk menyusul di iterasi berikutnya — saat ini menampilkan nilai
                terkini (live via WebSocket).
              </p>
            </template>
          </div>

          <div v-else-if="activeTab === 'software'" class="space-y-3">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <input
                v-model="softwareSearch"
                type="text"
                placeholder="Cari nama atau publisher..."
                class="w-64 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <button
                class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                :disabled="softwareList.length === 0"
                @click="exportSoftwareCsv"
              >
                Export CSV
              </button>
            </div>
            <div class="overflow-x-auto rounded-lg border border-slate-100">
              <table class="min-w-full divide-y divide-slate-100 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  <tr>
                    <th class="px-4 py-2">Software</th>
                    <th class="px-4 py-2">Versi</th>
                    <th class="px-4 py-2">Publisher</th>
                    <th class="px-4 py-2">Tanggal Install</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-if="isSoftwareLoading">
                    <td colspan="4" class="px-4 py-6 text-center text-slate-400">Memuat data...</td>
                  </tr>
                  <tr v-else-if="softwareList.length === 0">
                    <td colspan="4" class="px-4 py-6 text-center text-slate-400">
                      Belum ada data software. Muncul otomatis setelah agent sync (maks. 1 jam sekali).
                    </td>
                  </tr>
                  <tr v-for="item in softwareList" v-else :key="item.id" class="hover:bg-slate-50">
                    <td class="px-4 py-2 font-medium text-slate-700">{{ item.name }}</td>
                    <td class="px-4 py-2 text-slate-500">{{ item.version || '-' }}</td>
                    <td class="px-4 py-2 text-slate-500">{{ item.publisher || '-' }}</td>
                    <td class="px-4 py-2 text-slate-500">{{ item.install_date || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-else-if="activeTab === 'location'" class="space-y-4">
            <div v-if="isLocationLoading" class="py-10 text-center text-sm text-slate-400">Memuat data...</div>
            <template v-else-if="locationHistory.length === 0">
              <div class="py-10 text-center text-sm text-slate-400">
                Belum ada data lokasi. Muncul otomatis setelah agent sync (maks. 15 menit sekali).
              </div>
            </template>
            <template v-else>
              <div v-if="currentLocation.latitude !== null" class="space-y-3">
                <div class="rounded-lg border border-slate-100 p-2">
                  <LeafletMap :markers="locationMarkers" height="280px" />
                </div>
                <p class="text-xs text-slate-400">
                  Sumber: <strong>{{ currentLocation.source === 'OS' ? 'Windows Location Service' : 'Estimasi IP geolocation (perkiraan, bukan koordinat presisi)' }}</strong>
                  &middot; akurasi ±{{ Math.round(currentLocation.accuracy_meters || 0) }} m
                  &middot; {{ timeAgo(currentLocation.recorded_at) }}
                </p>
              </div>
              <div v-else class="rounded-lg bg-slate-50 p-4 text-sm text-slate-500">
                Lokasi terkini tidak diketahui — Windows Location Service tidak tersedia dan alamat IP
                device tidak bisa diestimasi (kemungkinan jaringan lokal/privat).
              </div>

              <div>
                <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Riwayat Lokasi</h3>
                <div class="overflow-x-auto rounded-lg border border-slate-100">
                  <table class="min-w-full divide-y divide-slate-100 text-sm">
                    <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                      <tr>
                        <th class="px-4 py-2">Waktu</th>
                        <th class="px-4 py-2">Sumber</th>
                        <th class="px-4 py-2">Koordinat</th>
                        <th class="px-4 py-2">Akurasi</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                      <tr v-for="loc in locationHistory" :key="loc.id" class="hover:bg-slate-50">
                        <td class="px-4 py-2 text-slate-500">{{ timeAgo(loc.recorded_at) }}</td>
                        <td class="px-4 py-2">
                          <span
                            class="rounded-full px-2 py-0.5 text-xs font-medium"
                            :class="loc.source === 'OS' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'"
                          >
                            {{ loc.source === 'OS' ? 'OS Location' : 'Estimasi IP' }}
                          </span>
                        </td>
                        <td class="px-4 py-2 font-mono text-xs text-slate-600">
                          {{ loc.latitude !== null ? `${loc.latitude.toFixed(5)}, ${loc.longitude.toFixed(5)}` : 'Tidak diketahui' }}
                        </td>
                        <td class="px-4 py-2 text-slate-500">
                          {{ loc.accuracy_meters ? `±${Math.round(loc.accuracy_meters)} m` : '-' }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </template>
          </div>

          <div v-else-if="activeTab === 'live-screen'">
            <LiveScreenPanel :key="device.device_id" :device-id="device.device_id" />
          </div>

          <div v-else class="py-10 text-center text-sm text-slate-400">
            Tab ini tersedia di phase berikutnya sesuai roadmap.
          </div>
        </div>
      </div>
    </template>

    <ConfirmDialog
      :open="confirmOpen"
      :title="toggleAction === 'disable' ? 'Nonaktifkan device?' : 'Aktifkan kembali device?'"
      :message="`${device?.device_id} akan di-${toggleAction === 'disable' ? 'nonaktifkan' : 'aktifkan kembali'}.`"
      :confirm-label="toggleAction === 'disable' ? 'Disable' : 'Enable'"
      :danger="toggleAction === 'disable'"
      @confirm="confirmToggle"
      @cancel="confirmOpen = false"
    />
  </div>
</template>
