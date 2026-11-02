<script setup>
import { onMounted, ref, watch } from 'vue'

import Pagination from '@/components/Pagination.vue'
import api from '@/services/api'
import { listAlerts } from '@/services/alerts'
import { useMonitoringStore } from '@/stores/monitoring'
import { downloadCsv } from '@/utils/csv'
import { timeAgo } from '@/utils/time'

const PAGE_SIZE = 25
const monitoring = useMonitoringStore()

const rows = ref([])
const isLoading = ref(true)
const isExporting = ref(false)
const errorMessage = ref('')
const statusFilter = ref('')
const severityFilter = ref('')
const categoryFilter = ref('')
const pageCount = ref(0)
const currentPage = ref(1)
const nextUrl = ref(null)
const previousUrl = ref(null)

const STATUS_OPTIONS = ['OPEN', 'ACKNOWLEDGED', 'RESOLVED']
const SEVERITY_OPTIONS = ['WARNING', 'CRITICAL']
const CATEGORY_OPTIONS = [
  'CPU',
  'RAM',
  'DISK',
  'BATTERY',
  'CONNECTIVITY',
  'USB',
  'OUT_OF_HOURS',
  'DATA_EXFIL',
  'NEW_SOFTWARE',
  'SUSPICIOUS_URL',
  'SYSTEM_ERROR',
]

const SEVERITY_STYLE = {
  WARNING: 'bg-amber-100 text-amber-700',
  CRITICAL: 'bg-red-100 text-red-700',
}
const STATUS_STYLE = {
  OPEN: 'bg-red-50 text-red-600',
  ACKNOWLEDGED: 'bg-amber-50 text-amber-700',
  RESOLVED: 'bg-emerald-50 text-emerald-700',
}

async function fetchAlerts(url = null) {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = url
      ? await api.get(url, { baseURL: '' })
      : await listAlerts({
          status: statusFilter.value || undefined,
          severity: severityFilter.value || undefined,
          category: categoryFilter.value || undefined,
        })
    rows.value = data.results
    pageCount.value = data.count
    nextUrl.value = data.next
    previousUrl.value = data.previous
  } catch {
    errorMessage.value = 'Gagal memuat data alerts.'
  } finally {
    isLoading.value = false
  }
}

function goNext() {
  if (!nextUrl.value) return
  currentPage.value += 1
  fetchAlerts(nextUrl.value)
}

function goPrevious() {
  if (!previousUrl.value) return
  currentPage.value -= 1
  fetchAlerts(previousUrl.value)
}

async function exportCsv() {
  isExporting.value = true
  try {
    const { data } = await listAlerts({
      status: statusFilter.value || undefined,
      severity: severityFilter.value || undefined,
      category: categoryFilter.value || undefined,
      page_size: 500,
    })
    downloadCsv('alerts.csv', data.results || [], [
      { header: 'Waktu Trigger', value: (r) => r.triggered_at },
      { header: 'Device ID', value: (r) => r.device_id },
      { header: 'Karyawan', value: (r) => r.assigned_employee || '' },
      { header: 'Kategori', value: (r) => r.category },
      { header: 'Severity', value: (r) => r.severity },
      { header: 'Status', value: (r) => r.status },
      { header: 'Pesan', value: (r) => r.message },
      { header: 'Waktu Selesai', value: (r) => r.resolved_at || '' },
    ])
  } finally {
    isExporting.value = false
  }
}

watch([statusFilter, severityFilter, categoryFilter], () => {
  currentPage.value = 1
  fetchAlerts()
})
watch(
  () => monitoring.lastAlertEventAt,
  () => {
    if (currentPage.value === 1) fetchAlerts()
  },
)
onMounted(fetchAlerts)
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-slate-800">Alerts</h1>
      <div class="flex flex-wrap gap-2">
        <select
          v-model="statusFilter"
          class="min-w-[9rem] flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 sm:flex-none"
        >
          <option value="">Semua Status</option>
          <option v-for="s in STATUS_OPTIONS" :key="s" :value="s">{{ s }}</option>
        </select>
        <select
          v-model="severityFilter"
          class="min-w-[9rem] flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 sm:flex-none"
        >
          <option value="">Semua Severity</option>
          <option v-for="s in SEVERITY_OPTIONS" :key="s" :value="s">{{ s }}</option>
        </select>
        <select
          v-model="categoryFilter"
          class="min-w-[9rem] flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 sm:flex-none"
        >
          <option value="">Semua Kategori</option>
          <option v-for="c in CATEGORY_OPTIONS" :key="c" :value="c">{{ c }}</option>
        </select>
        <button
          :disabled="isExporting || rows.length === 0"
          class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          @click="exportCsv"
        >
          {{ isExporting ? 'Mengekspor...' : 'Export CSV' }}
        </button>
      </div>
    </div>

    <div v-if="isLoading" class="rounded-xl bg-white p-8 text-center text-slate-400 shadow-sm ring-1 ring-slate-900/5">
      Memuat data...
    </div>
    <div v-else-if="errorMessage" class="rounded-xl bg-white p-8 text-center text-red-500 shadow-sm ring-1 ring-slate-900/5">
      {{ errorMessage }}
    </div>
    <div v-else-if="rows.length === 0" class="rounded-xl bg-white p-8 text-center text-slate-400 shadow-sm ring-1 ring-slate-900/5">
      Tidak ada alert.
    </div>

    <!-- Mobile: stacked cards -->
    <div v-else class="space-y-3 md:hidden">
      <div v-for="alert in rows" :key="alert.id" class="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-900/5">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate font-medium text-slate-700">{{ alert.assigned_employee || '-' }}</p>
            <p class="truncate font-mono text-xs text-slate-400">{{ alert.device_id }}</p>
          </div>
          <span class="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="STATUS_STYLE[alert.status]">
            {{ alert.status }}
          </span>
        </div>
        <div class="mt-3">
          <span class="mb-1 inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="SEVERITY_STYLE[alert.severity]">
            {{ alert.severity }}
          </span>
          <p class="break-words text-sm text-slate-600">{{ alert.message }}</p>
        </div>
        <div class="mt-3">
          <span class="text-xs text-slate-500">{{ timeAgo(alert.triggered_at) }}</span>
        </div>
      </div>
    </div>

    <!-- Desktop/tablet: table -->
    <div v-if="!isLoading && !errorMessage && rows.length > 0" class="hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5 md:block">
      <table class="w-full table-fixed divide-y divide-slate-200 text-sm">
        <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th class="w-[20%] px-4 py-3">Perangkat</th>
            <th class="w-[48%] px-4 py-3">Alert</th>
            <th class="w-[14%] px-4 py-3">Status</th>
            <th class="w-[18%] px-4 py-3">Terjadi</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="alert in rows" :key="alert.id" class="hover:bg-slate-50">
            <td class="px-4 py-3 align-top">
              <div class="truncate text-slate-700">{{ alert.assigned_employee || '-' }}</div>
              <div class="truncate font-mono text-xs text-slate-400">{{ alert.device_id }}</div>
            </td>
            <td class="px-4 py-3 align-top">
              <span
                class="mb-1 inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold"
                :class="SEVERITY_STYLE[alert.severity]"
              >
                {{ alert.severity }}
              </span>
              <div class="break-words text-slate-600">{{ alert.message }}</div>
            </td>
            <td class="px-4 py-3 align-top">
              <span class="rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="STATUS_STYLE[alert.status]">
                {{ alert.status }}
              </span>
            </td>
            <td class="px-4 py-3 align-top text-slate-500">{{ timeAgo(alert.triggered_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <Pagination
      v-if="!isLoading && rows.length > 0"
      :page="currentPage"
      :page-size="PAGE_SIZE"
      :count="pageCount"
      :has-previous="Boolean(previousUrl)"
      :has-next="Boolean(nextUrl)"
      @previous="goPrevious"
      @next="goNext"
    />
  </div>
</template>
