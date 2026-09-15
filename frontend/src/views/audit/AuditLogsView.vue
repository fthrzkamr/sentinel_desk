<script setup>
import { onMounted, ref, watch } from 'vue'

import api from '@/services/api'
import { listAuditLogs } from '@/services/audit'

const rows = ref([])
const isLoading = ref(true)
const errorMessage = ref('')
const search = ref('')
const actionFilter = ref('')
const usernameFilter = ref('')
const deviceFilter = ref('')
const pageCount = ref(0)
const nextUrl = ref(null)
const previousUrl = ref(null)

// Every distinct `action` string any part of the backend actually writes via
// log_action() — kept as an explicit dropdown (instead of free text) so this
// filter always matches something real instead of requiring the exact string.
const ACTION_GROUPS = [
  { label: 'Auth', actions: ['auth.login', 'auth.login_failed', 'auth.logout'] },
  { label: 'Device', actions: ['device.registered', 'device.disabled', 'device.enabled'] },
  {
    label: 'Agent',
    actions: ['agent.enrollment_token_created', 'agent.enrollment_token_revoked', 'agent.enroll_failed'],
  },
  { label: 'Live Screen', actions: ['livescreen.started', 'livescreen.stopped', 'livescreen.start_failed'] },
  { label: 'Alert', actions: ['alert.acknowledged', 'alert.resolved'] },
  {
    label: 'User',
    actions: ['user.created', 'user.updated', 'user.activated', 'user.deactivated', 'user.password_reset'],
  },
]

async function fetchLogs(url = null) {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = url
      ? await api.get(url)
      : await listAuditLogs({
          search: search.value || undefined,
          action: actionFilter.value || undefined,
          username: usernameFilter.value || undefined,
          device_id: deviceFilter.value || undefined,
        })
    rows.value = data.results
    pageCount.value = data.count
    nextUrl.value = data.next
    previousUrl.value = data.previous
  } catch {
    errorMessage.value = 'Gagal memuat audit log.'
  } finally {
    isLoading.value = false
  }
}

let searchDebounce = null
watch([search, actionFilter, usernameFilter, deviceFilter], () => {
  clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => fetchLogs(), 300)
})

onMounted(fetchLogs)

function formatMetadata(metadata) {
  if (!metadata || Object.keys(metadata).length === 0) return '-'
  return Object.entries(metadata)
    .map(([key, value]) => `${key}=${value}`)
    .join(', ')
}
</script>

<template>
  <div class="space-y-4">
    <div>
      <h1 class="text-xl font-semibold text-slate-800">Audit Logs</h1>
      <p class="mt-1 text-xs text-slate-400">
        Catatan aktivitas administratif yang sensitif (login, live screen, disable device, manajemen user, dll).
        Read-only — tidak bisa diedit atau dihapus dari mana pun, termasuk di sini.
      </p>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-900/5">
      <div>
        <label class="mb-1 block text-xs font-medium text-slate-600">Cari (bebas)</label>
        <input
          v-model="search"
          type="text"
          placeholder="action, device ID, atau username..."
          class="w-56 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-slate-600">Action</label>
        <select
          v-model="actionFilter"
          class="w-52 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">Semua Action</option>
          <optgroup v-for="group in ACTION_GROUPS" :key="group.label" :label="group.label">
            <option v-for="action in group.actions" :key="action" :value="action">{{ action }}</option>
          </optgroup>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-slate-600">User</label>
        <input
          v-model="usernameFilter"
          type="text"
          placeholder="username persis"
          class="w-36 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-slate-600">Device ID</label>
        <input
          v-model="deviceFilter"
          type="text"
          placeholder="mis. SD-LPT-000001"
          class="w-40 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
      </div>
      <button
        v-if="search || actionFilter || usernameFilter || deviceFilter"
        class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-50"
        @click="search = ''; actionFilter = ''; usernameFilter = ''; deviceFilter = ''"
      >
        Reset Filter
      </button>
    </div>

    <div class="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th class="px-4 py-3">Waktu</th>
            <th class="px-4 py-3">User</th>
            <th class="px-4 py-3">Action</th>
            <th class="px-4 py-3">Device</th>
            <th class="px-4 py-3">IP</th>
            <th class="px-4 py-3">Detail</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-if="isLoading">
            <td colspan="6" class="px-4 py-8 text-center text-slate-400">Memuat data...</td>
          </tr>
          <tr v-else-if="errorMessage">
            <td colspan="6" class="px-4 py-8 text-center text-red-500">{{ errorMessage }}</td>
          </tr>
          <tr v-else-if="rows.length === 0">
            <td colspan="6" class="px-4 py-8 text-center text-slate-400">Belum ada aktivitas tercatat.</td>
          </tr>
          <tr v-for="log in rows" v-else :key="log.id" class="hover:bg-slate-50">
            <td class="px-4 py-3 whitespace-nowrap text-slate-500">{{ new Date(log.created_at).toLocaleString() }}</td>
            <td class="px-4 py-3 text-slate-600">{{ log.username || 'System' }}</td>
            <td class="px-4 py-3 font-mono text-xs text-brand-700">{{ log.action }}</td>
            <td class="px-4 py-3 font-mono text-xs text-slate-500">{{ log.device_id || '-' }}</td>
            <td class="px-4 py-3 text-slate-500">{{ log.ip_address || '-' }}</td>
            <td class="px-4 py-3 text-xs text-slate-500">{{ formatMetadata(log.metadata) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="!isLoading && rows.length > 0" class="flex items-center justify-between text-sm text-slate-500">
      <span>{{ pageCount }} entri total</span>
      <div class="flex gap-2">
        <button class="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40" :disabled="!previousUrl" @click="fetchLogs(previousUrl)">
          Previous
        </button>
        <button class="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40" :disabled="!nextUrl" @click="fetchLogs(nextUrl)">
          Next
        </button>
      </div>
    </div>
  </div>
</template>
