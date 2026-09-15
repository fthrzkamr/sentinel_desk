<script setup>
import { onMounted, reactive, ref } from 'vue'

import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { createEnrollmentToken, listEnrollmentTokens, revokeEnrollmentToken } from '@/services/devices'

const tokens = ref([])
const isLoading = ref(true)
const errorMessage = ref('')

const form = reactive({ label: '', ttl_minutes: 60 })
const isCreating = ref(false)
const revealedToken = ref(null)
const copyLabel = ref('Copy')

const confirmState = reactive({ open: false, token: null })

async function fetchTokens() {
  isLoading.value = true
  try {
    const { data } = await listEnrollmentTokens()
    tokens.value = data.results ?? data
  } catch (error) {
    errorMessage.value = 'Gagal memuat daftar enrollment token.'
  } finally {
    isLoading.value = false
  }
}

onMounted(fetchTokens)

async function handleCreate() {
  isCreating.value = true
  errorMessage.value = ''
  try {
    const { data } = await createEnrollmentToken({
      label: form.label,
      ttl_minutes: form.ttl_minutes,
    })
    revealedToken.value = data
    form.label = ''
    await fetchTokens()
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || 'Gagal membuat enrollment token.'
  } finally {
    isCreating.value = false
  }
}

async function copyToken() {
  try {
    await navigator.clipboard.writeText(revealedToken.value.token)
    copyLabel.value = 'Copied!'
    setTimeout(() => (copyLabel.value = 'Copy'), 1500)
  } catch {
    copyLabel.value = 'Gagal copy'
  }
}

function askRevoke(token) {
  confirmState.open = true
  confirmState.token = token
}

async function confirmRevoke() {
  confirmState.open = false
  try {
    await revokeEnrollmentToken(confirmState.token.id)
    await fetchTokens()
  } catch (error) {
    errorMessage.value = 'Gagal me-revoke token.'
  }
}

function tokenStatus(token) {
  if (token.revoked) return { label: 'Revoked', cls: 'bg-slate-300 text-slate-600' }
  if (token.used_at) return { label: 'Used', cls: 'bg-blue-100 text-blue-700' }
  if (!token.is_valid) return { label: 'Expired', cls: 'bg-amber-100 text-amber-700' }
  return { label: 'Valid', cls: 'bg-emerald-100 text-emerald-700' }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-semibold text-slate-800">Agent Management</h1>
    </div>

    <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
      <h2 class="text-sm font-semibold text-slate-700">Buat Enrollment Token</h2>
      <p class="mt-1 text-xs text-slate-500">
        Token dipakai sekali oleh SentinelDesk Agent saat pertama kali enroll. Setelah dipakai atau
        kedaluwarsa, token tidak bisa dipakai lagi.
      </p>
      <form class="mt-3 flex flex-wrap items-end gap-3" @submit.prevent="handleCreate">
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Label (opsional)</label>
          <input
            v-model="form.label"
            type="text"
            placeholder="mis. laptop-budi"
            class="w-52 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Berlaku (menit)</label>
          <input
            v-model.number="form.ttl_minutes"
            type="number"
            min="1"
            max="10080"
            class="w-28 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>
        <button
          type="submit"
          :disabled="isCreating"
          class="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {{ isCreating ? 'Membuat...' : 'Buat Token' }}
        </button>
      </form>

      <div v-if="revealedToken" class="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-4">
        <p class="text-sm font-medium text-amber-800">
          Token ini hanya ditampilkan sekali — simpan sekarang.
        </p>
        <div class="mt-2 flex items-center gap-2">
          <code class="flex-1 overflow-x-auto rounded bg-white px-3 py-2 text-xs">{{ revealedToken.token }}</code>
          <button
            class="rounded-md border border-amber-400 px-3 py-2 text-xs font-medium text-amber-800 hover:bg-amber-100"
            @click="copyToken"
          >
            {{ copyLabel }}
          </button>
        </div>
        <p class="mt-2 text-xs text-amber-700">
          Isi ke <code>agent/.env</code> pada baris <code>ENROLLMENT_TOKEN=</code>, lalu jalankan
          <code>python src/main.py</code> di komputer yang akan didaftarkan. Berlaku sampai
          {{ new Date(revealedToken.expires_at).toLocaleString() }}.
        </p>
      </div>

      <p v-if="errorMessage" class="mt-3 text-sm text-red-600">{{ errorMessage }}</p>
    </div>

    <div class="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th class="px-4 py-3">Prefix</th>
            <th class="px-4 py-3">Label</th>
            <th class="px-4 py-3">Dibuat oleh</th>
            <th class="px-4 py-3">Kedaluwarsa</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Device</th>
            <th class="px-4 py-3 text-right">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-if="isLoading">
            <td colspan="7" class="px-4 py-8 text-center text-slate-400">Memuat data...</td>
          </tr>
          <tr v-else-if="tokens.length === 0">
            <td colspan="7" class="px-4 py-8 text-center text-slate-400">Belum ada enrollment token.</td>
          </tr>
          <tr v-for="token in tokens" v-else :key="token.id" class="hover:bg-slate-50">
            <td class="px-4 py-3 font-mono text-xs">{{ token.token_prefix }}...</td>
            <td class="px-4 py-3">{{ token.label || '-' }}</td>
            <td class="px-4 py-3">{{ token.created_by || '-' }}</td>
            <td class="px-4 py-3">{{ new Date(token.expires_at).toLocaleString() }}</td>
            <td class="px-4 py-3">
              <span class="inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="tokenStatus(token).cls">
                {{ tokenStatus(token).label }}
              </span>
            </td>
            <td class="px-4 py-3 font-mono text-xs">{{ token.used_by_device || '-' }}</td>
            <td class="px-4 py-3 text-right">
              <button
                v-if="!token.revoked && !token.used_at"
                class="text-red-600 hover:underline"
                @click="askRevoke(token)"
              >
                Revoke
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ConfirmDialog
      :open="confirmState.open"
      title="Revoke enrollment token?"
      :message="`Token dengan prefix ${confirmState.token?.token_prefix}... tidak akan bisa dipakai lagi.`"
      confirm-label="Revoke"
      danger
      @confirm="confirmRevoke"
      @cancel="confirmState.open = false"
    />
  </div>
</template>
