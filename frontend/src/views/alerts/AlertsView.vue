<script setup>
import { onMounted, ref, watch } from 'vue'

import api from '@/services/api'
import { acknowledgeAlert, listAlerts, resolveAlert } from '@/services/alerts'
import { useAuthStore } from '@/stores/auth'
import { useMonitoringStore } from '@/stores/monitoring'
import { timeAgo } from '@/utils/time'

const auth = useAuthStore()
const monitoring = useMonitoringStore()

const rows = ref([])
const isLoading = ref(true)
const errorMessage = ref('')
const statusFilter = ref('')
const severityFilter = ref('')
const categoryFilter = ref('')
const pageCount = ref(0)
const nextUrl = ref(null)
const previousUrl = ref(null)
const actioningId = ref(null)

const STATUS_OPTIONS = ['OPEN', 'ACKNOWLEDGED', 'RESOLVED']
const SEVERITY_OPTIONS = ['WARNING', 'CRITICAL']
const CATEGORY_OPTIONS = ['CPU', 'RAM', 'DISK', 'BATTERY', 'CONNECTIVITY', 'USB', 'OUT_OF_HOURS', 'DATA_EXFIL']

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
      ? await api.get(url)
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

watch([statusFilter, severityFilter, categoryFilter], () => fetchAlerts())
onMounted(fetchAlerts)

async function handleAcknowledge(alert) {
  actioningId.value = alert.id
  try {
    await acknowledgeAlert(alert.id)
    await fetchAlerts()
    monitoring.fetchAlertSummary()
  } catch {
    errorMessage.value = 'Gagal acknowledge alert.'
  } finally {
    actioningId.value = null
  }
}

async function handleResolve(alert) {
  actioningId.value = alert.id
  try {
    await resolveAlert(alert.id)
    await fetchAlerts()
    monitoring.fetchAlertSummary()
  } catch {
    errorMessage.value = 'Gagal resolve alert.'
  } finally {
    actioningId.value = null
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-slate-800">Alerts</h1>
      <div class="flex flex-wrap gap-2">
        <select
          v-model="statusFilter"
          class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">Semua Status</option>
          <option v-for="s in STATUS_OPTIONS" :key="s" :value="s">{{ s }}</option>
        </select>
        <select
          v-model="severityFilter"
          class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">Semua Severity</option>
          <option v-for="s in SEVERITY_OPTIONS" :key="s" :value="s">{{ s }}</option>
        </select>
        <select
          v-model="categoryFilter"
          class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">Semua Kategori</option>
          <option v-for="c in CATEGORY_OPTIONS" :key="c" :value="c">{{ c }}</option>
        </select>
      </div>
    </div>

    <div class="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th class="px-4 py-3">Device</th>
            <th class="px-4 py-3">Karyawan</th>
            <th class="px-4 py-3">Kategori</th>
            <th class="px-4 py-3">Severity</th>
            <th class="px-4 py-3">Pesan</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Terjadi</th>
            <th class="px-4 py-3 text-right">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-if="isLoading">
            <td colspan="8" class="px-4 py-8 text-center text-slate-400">Memuat data...</td>
          </tr>
          <tr v-else-if="errorMessage">
            <td colspan="8" class="px-4 py-8 text-center text-red-500">{{ errorMessage }}</td>
          </tr>
          <tr v-else-if="rows.length === 0">
            <td colspan="8" class="px-4 py-8 text-center text-slate-400">Tidak ada alert.</td>
          </tr>
          <tr v-for="alert in rows" v-else :key="alert.id" class="hover:bg-slate-50">
            <td class="px-4 py-3 font-mono text-xs text-slate-600">{{ alert.device_id }}</td>
            <td class="px-4 py-3 text-slate-600">
              {{ alert.assigned_employee || '-' }}
            </td>
            <td class="px-4 py-3 text-slate-600">{{ alert.category }}</td>
            <td class="px-4 py-3">
              <span class="rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="SEVERITY_STYLE[alert.severity]">
                {{ alert.severity }}
              </span>
            </td>
            <td class="px-4 py-3 text-slate-600">{{ alert.message }}</td>
            <td class="px-4 py-3">
              <span class="rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="STATUS_STYLE[alert.status]">
                {{ alert.status }}
              </span>
            </td>
            <td class="px-4 py-3 text-slate-500">{{ timeAgo(alert.triggered_at) }}</td>
            <td class="px-4 py-3 text-right">
              <div v-if="auth.hasPermission('alert.manage')" class="flex justify-end gap-3">
                <button
                  v-if="alert.status === 'OPEN'"
                  class="text-amber-600 hover:underline disabled:opacity-50"
                  :disabled="actioningId === alert.id"
                  @click="handleAcknowledge(alert)"
                >
                  Acknowledge
                </button>
                <button
                  v-if="alert.status !== 'RESOLVED'"
                  class="text-emerald-600 hover:underline disabled:opacity-50"
                  :disabled="actioningId === alert.id"
                  @click="handleResolve(alert)"
                >
                  Resolve
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="!isLoading && rows.length > 0" class="flex items-center justify-between text-sm text-slate-500">
      <span>{{ pageCount }} entri total</span>
      <div class="flex gap-2">
        <button class="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40" :disabled="!previousUrl" @click="fetchAlerts(previousUrl)">
          Previous
        </button>
        <button class="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40" :disabled="!nextUrl" @click="fetchAlerts(nextUrl)">
          Next
        </button>
      </div>
    </div>
  </div>
</template>
