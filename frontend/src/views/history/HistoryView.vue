<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import MetricTrendChart from '@/components/MetricTrendChart.vue'
import { listDevices } from '@/services/devices'
import { getMetricHistory } from '@/services/monitoring'

const router = useRouter()

const devices = ref([])
const selectedDeviceId = ref('')
const samples = ref([])
const isLoadingDevices = ref(true)
const isLoadingHistory = ref(false)
const errorMessage = ref('')

async function fetchDevices() {
  isLoadingDevices.value = true
  try {
    const { data } = await listDevices({ page_size: 200 })
    devices.value = data.results
    if (devices.value.length > 0) {
      selectedDeviceId.value = devices.value[0].device_id
    }
  } catch {
    errorMessage.value = 'Gagal memuat daftar device.'
  } finally {
    isLoadingDevices.value = false
  }
}

async function fetchHistory() {
  if (!selectedDeviceId.value) return
  isLoadingHistory.value = true
  errorMessage.value = ''
  try {
    const { data } = await getMetricHistory(selectedDeviceId.value, { page_size: 200 })
    samples.value = [...data.results].reverse()
  } catch {
    errorMessage.value = 'Gagal memuat riwayat metrics device ini.'
    samples.value = []
  } finally {
    isLoadingHistory.value = false
  }
}

watch(selectedDeviceId, fetchHistory)

onMounted(async () => {
  await fetchDevices()
  await fetchHistory()
})
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-slate-800">History</h1>
      <select
        v-if="!isLoadingDevices && devices.length > 0"
        v-model="selectedDeviceId"
        class="w-64 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
      >
        <option v-for="device in devices" :key="device.device_id" :value="device.device_id">
          {{ device.device_id }} — {{ device.hostname }}
        </option>
      </select>
    </div>

    <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
      <div v-if="isLoadingDevices" class="py-10 text-center text-sm text-slate-400">Memuat data...</div>
      <div v-else-if="devices.length === 0" class="flex flex-col items-center gap-3 py-14 text-center">
        <p class="text-sm text-slate-500">Belum ada device yang terdaftar di sistem ini.</p>
        <p class="max-w-sm text-xs text-slate-400">
          Jalankan SentinelDesk Agent di komputer yang mau dipantau — daftarkan lewat enrollment token dari halaman
          Agents, lalu grafik di sini otomatis muncul begitu agent mulai mengirim data.
        </p>
        <button
          class="mt-1 rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
          @click="router.push({ name: 'agents' })"
        >
          Buka halaman Agents
        </button>
      </div>
      <div v-else-if="errorMessage" class="py-10 text-center text-sm text-red-500">{{ errorMessage }}</div>
      <div v-else-if="isLoadingHistory" class="py-10 text-center text-sm text-slate-400">Memuat grafik...</div>
      <MetricTrendChart v-else :samples="samples" />
    </div>

    <p class="text-xs text-slate-400">
      Riwayat CPU/RAM/Disk per device. Untuk riwayat lokasi, lihat halaman Map atau tab Location di Device Detail.
    </p>
  </div>
</template>
