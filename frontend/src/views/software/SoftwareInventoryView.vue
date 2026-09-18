<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import api from '@/services/api'
import { listDevices } from '@/services/devices'
import { listSoftware } from '@/services/software'
import { downloadCsv } from '@/utils/csv'

const rows = ref([])
const isLoading = ref(false)
const isExporting = ref(false)
const errorMessage = ref('')
const search = ref('')
const deviceFilter = ref('')
const ordering = ref('name')
const pageCount = ref(0)
const currentUrl = ref(null)
const nextUrl = ref(null)
const previousUrl = ref(null)

const devices = ref([])
const isLoadingDevices = ref(true)
const deviceSearch = ref('')

const filteredDevices = computed(() => {
  const term = deviceSearch.value.trim().toLowerCase()
  if (!term) return devices.value
  return devices.value.filter(
    (d) =>
      d.device_id.toLowerCase().includes(term) ||
      d.hostname?.toLowerCase().includes(term) ||
      d.assigned_employee?.toLowerCase().includes(term),
  )
})

const columns = [
  { key: 'name', label: 'Software' },
  { key: 'version', label: 'Versi' },
  { key: 'publisher', label: 'Publisher' },
  { key: 'install_date', label: 'Tanggal Install' },
]

const selectedDevice = computed(() => devices.value.find((d) => d.device_id === deviceFilter.value) || null)

async function fetchDevices() {
  isLoadingDevices.value = true
  try {
    const { data } = await listDevices({ page_size: 200 })
    devices.value = data.results
  } finally {
    isLoadingDevices.value = false
  }
}

async function fetchSoftware(url = null) {
  if (!deviceFilter.value) {
    rows.value = []
    pageCount.value = 0
    return
  }

  isLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = url
      ? await api.get(url)
      : await listSoftware({
          search: search.value || undefined,
          device: deviceFilter.value,
          ordering: ordering.value,
        })

    rows.value = data.results
    pageCount.value = data.count
    nextUrl.value = data.next
    previousUrl.value = data.previous
    currentUrl.value = url
  } catch (error) {
    errorMessage.value = 'Gagal memuat data software.'
  } finally {
    isLoading.value = false
  }
}

let searchDebounce = null
watch([search, deviceFilter, ordering], () => {
  clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => fetchSoftware(), 300)
})

onMounted(fetchDevices)

function toggleSort(key) {
  ordering.value = ordering.value === key ? `-${key}` : key
}

function sortIndicator(key) {
  if (ordering.value === key) return '▲'
  if (ordering.value === `-${key}`) return '▼'
  return ''
}

async function exportCsv() {
  if (!deviceFilter.value) return
  isExporting.value = true
  try {
    const { data } = await listSoftware({
      search: search.value || undefined,
      device: deviceFilter.value,
      ordering: ordering.value,
      page_size: 1000,
    })
    downloadCsv(`software-${deviceFilter.value}.csv`, data.results, columns)
  } catch {
    errorMessage.value = 'Gagal mengekspor data.'
  } finally {
    isExporting.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-slate-800">Software Inventory</h1>
      <div class="flex flex-wrap gap-2">
        <input
          v-model="deviceSearch"
          type="text"
          placeholder="Cari nama karyawan, hostname, atau device ID..."
          class="w-64 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <select
          v-model="deviceFilter"
          class="w-64 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">{{ isLoadingDevices ? 'Memuat device...' : 'Pilih device...' }}</option>
          <option v-for="d in filteredDevices" :key="d.device_id" :value="d.device_id">
            {{ d.device_id }} — {{ d.hostname }}{{ d.assigned_employee ? ` (${d.assigned_employee})` : '' }}
          </option>
        </select>
        <input
          v-model="search"
          type="text"
          placeholder="Cari nama atau publisher..."
          :disabled="!deviceFilter"
          class="w-56 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 disabled:cursor-not-allowed disabled:bg-slate-50"
        />
        <button
          class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          :disabled="isExporting || !deviceFilter"
          @click="exportCsv"
        >
          {{ isExporting ? 'Mengekspor...' : 'Export CSV' }}
        </button>
      </div>
    </div>

    <div v-if="!deviceFilter" class="rounded-xl bg-white p-10 text-center text-sm text-slate-400 shadow-sm ring-1 ring-slate-900/5">
      Pilih device terlebih dahulu di atas untuk melihat daftar software yang terinstall.
    </div>

    <template v-else>
      <p class="text-xs text-slate-400">
        Menampilkan software untuk <strong class="text-slate-600">{{ selectedDevice?.hostname || deviceFilter }}</strong>
      </p>

      <div class="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
        <table class="min-w-full divide-y divide-slate-200 text-sm">
          <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
            <tr>
              <th
                v-for="col in columns"
                :key="col.key"
                class="cursor-pointer select-none px-4 py-3 hover:text-slate-700"
                @click="toggleSort(col.key)"
              >
                {{ col.label }} <span class="text-brand-500">{{ sortIndicator(col.key) }}</span>
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-if="isLoading">
              <td :colspan="columns.length" class="px-4 py-8 text-center text-slate-400">Memuat data...</td>
            </tr>
            <tr v-else-if="errorMessage">
              <td :colspan="columns.length" class="px-4 py-8 text-center text-red-500">{{ errorMessage }}</td>
            </tr>
            <tr v-else-if="rows.length === 0">
              <td :colspan="columns.length" class="px-4 py-8 text-center text-slate-400">
                Belum ada data software untuk device ini. Software muncul otomatis setelah agent melakukan sync (maks. 1 jam sekali).
              </td>
            </tr>
            <tr v-for="row in rows" v-else :key="row.id" class="hover:bg-slate-50">
              <td class="px-4 py-3 font-medium text-slate-700">{{ row.name }}</td>
              <td class="px-4 py-3 text-slate-500">{{ row.version || '-' }}</td>
              <td class="px-4 py-3 text-slate-500">{{ row.publisher || '-' }}</td>
              <td class="px-4 py-3 text-slate-500">{{ row.install_date || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <div v-if="deviceFilter && !isLoading && rows.length > 0" class="flex items-center justify-between text-sm text-slate-500">
      <span>{{ pageCount }} entri total</span>
      <div class="flex gap-2">
        <button
          class="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
          :disabled="!previousUrl"
          @click="fetchSoftware(previousUrl)"
        >
          Previous
        </button>
        <button
          class="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
          :disabled="!nextUrl"
          @click="fetchSoftware(nextUrl)"
        >
          Next
        </button>
      </div>
    </div>
  </div>
</template>
