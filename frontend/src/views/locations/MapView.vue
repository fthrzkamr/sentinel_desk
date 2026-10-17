<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import LeafletMap from '@/components/LeafletMap.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { listLatestLocations } from '@/services/locations'
import { timeAgo } from '@/utils/time'

const router = useRouter()
const locations = ref([])
const isLoading = ref(true)
const errorMessage = ref('')

async function fetchLocations() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = await listLatestLocations()
    locations.value = data.results ?? data
  } catch {
    errorMessage.value = 'Gagal memuat data lokasi.'
  } finally {
    isLoading.value = false
  }
}

onMounted(fetchLocations)

const markers = computed(() =>
  locations.value
    .filter((loc) => loc.latitude !== null)
    .map((loc) => ({
      lat: loc.latitude,
      lng: loc.longitude,
      accuracy: loc.accuracy_meters,
      popupHtml: `<strong>${loc.device_id}</strong><br>${loc.hostname}<br>${
        loc.assigned_employee || 'Belum di-assign'
      }${loc.branch ? ` · ${loc.branch}` : ''}<br>Sumber: ${
        loc.source === 'OS' ? 'OS Location Service' : 'Estimasi IP'
      }`,
    })),
)

const withCoords = computed(() => locations.value.filter((loc) => loc.latitude !== null))
const withoutCoords = computed(() => locations.value.filter((loc) => loc.latitude === null))

function goToDevice(deviceId) {
  router.push({ name: 'device-detail', params: { deviceId } })
}
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-slate-800">Peta Lokasi Device</h1>
    <p class="text-sm text-slate-500">
      Lokasi berdasarkan Windows Location Service (akurat, dilingkari radius akurasi) atau estimasi
      IP geolocation (perkiraan level kota — <strong>bukan koordinat presisi</strong>).
    </p>

    <div v-if="isLoading" class="rounded-xl bg-white p-8 text-center text-slate-400 shadow-sm ring-1 ring-slate-900/5">
      Memuat data...
    </div>
    <div v-else-if="errorMessage" class="rounded-xl bg-white p-8 text-center text-red-500 shadow-sm ring-1 ring-slate-900/5">
      {{ errorMessage }}
    </div>
    <template v-else>
      <div class="rounded-xl bg-white p-3 shadow-sm ring-1 ring-slate-900/5">
        <LeafletMap :markers="markers" height="480px" />
      </div>

      <div class="rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
        <div class="border-b border-slate-100 px-5 py-3">
          <h2 class="text-sm font-semibold text-slate-700">
            Device dengan Lokasi ({{ withCoords.length }})
          </h2>
        </div>
        <table class="min-w-full divide-y divide-slate-100 text-sm">
          <thead class="text-left text-xs font-medium uppercase tracking-wide text-slate-500">
            <tr>
              <th class="px-5 py-2.5">Device ID</th>
              <th class="px-5 py-2.5">Hostname</th>
              <th class="px-5 py-2.5">Karyawan</th>
              <th class="px-5 py-2.5">Cabang</th>
              <th class="px-5 py-2.5">Sumber</th>
              <th class="px-5 py-2.5">Akurasi</th>
              <th class="px-5 py-2.5">Waktu</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-if="withCoords.length === 0">
              <td colspan="7" class="px-5 py-6 text-center text-slate-400">Belum ada device dengan lokasi diketahui.</td>
            </tr>
            <tr
              v-for="loc in withCoords"
              :key="loc.id"
              class="cursor-pointer hover:bg-slate-50"
              @click="goToDevice(loc.device_id)"
            >
              <td class="px-5 py-3 font-mono text-xs text-slate-600">{{ loc.device_id }}</td>
              <td class="px-5 py-3">{{ loc.hostname }}</td>
              <td class="px-5 py-3">{{ loc.assigned_employee || '-' }}</td>
              <td class="px-5 py-3 text-slate-500">{{ loc.branch || '-' }}</td>
              <td class="px-5 py-3">
                <span
                  class="rounded-full px-2 py-0.5 text-xs font-medium"
                  :class="loc.source === 'OS' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'"
                >
                  {{ loc.source === 'OS' ? 'OS Location' : 'Estimasi IP' }}
                </span>
              </td>
              <td class="px-5 py-3 text-slate-500">
                {{ loc.accuracy_meters ? `±${Math.round(loc.accuracy_meters)} m` : '-' }}
              </td>
              <td class="px-5 py-3 text-slate-500">{{ timeAgo(loc.recorded_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="withoutCoords.length > 0" class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <h2 class="text-sm font-semibold text-slate-700">
          Lokasi Tidak Diketahui ({{ withoutCoords.length }})
        </h2>
        <p class="mt-1 text-xs text-slate-400">
          OS Location Service tidak tersedia/ditolak, dan alamat IP device tidak bisa diestimasi
          (mis. jaringan lokal/privat).
        </p>
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            v-for="loc in withoutCoords"
            :key="loc.id"
            class="rounded-full border border-slate-200 px-3 py-1 text-xs font-mono text-slate-600 hover:bg-slate-50"
            @click="goToDevice(loc.device_id)"
          >
            {{ loc.device_id }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
