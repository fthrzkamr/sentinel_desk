<script setup>
import { onMounted, reactive, ref } from 'vue'

import ConfirmDialog from '@/components/ConfirmDialog.vue'
import StatusModal from '@/components/StatusModal.vue'
import { useAuthStore } from '@/stores/auth'
import {
  activateUser,
  createUser,
  deactivateUser,
  deleteUser,
  listRoles,
  listUsers,
  resetUserPassword,
  updateUser,
} from '@/services/users'

const auth = useAuthStore()

const users = ref([])
const roles = ref([])
const isLoading = ref(true)
const errorMessage = ref('')

const form = reactive({ username: '', email: '', password: '', role: '' })
const isCreating = ref(false)

const confirmState = reactive({ open: false, user: null, action: null })
const resetState = reactive({ open: false, user: null, newPassword: '' })
const status = reactive({ open: false, variant: 'success', title: '', message: '' })

async function fetchAll() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [usersRes, rolesRes] = await Promise.all([listUsers(), listRoles()])
    users.value = usersRes.data.results ?? usersRes.data
    roles.value = rolesRes.data.results ?? rolesRes.data
  } catch {
    errorMessage.value = 'Gagal memuat data user.'
  } finally {
    isLoading.value = false
  }
}

onMounted(fetchAll)

function showStatus(variant, title, message = '') {
  status.variant = variant
  status.title = title
  status.message = message
  status.open = true
}

async function handleCreate() {
  isCreating.value = true
  errorMessage.value = ''
  try {
    await createUser({
      username: form.username,
      email: form.email,
      password: form.password,
      role: form.role || null,
    })
    form.username = ''
    form.email = ''
    form.password = ''
    form.role = ''
    await fetchAll()
    showStatus('success', 'User berhasil dibuat', 'Beritahu password awal kepada user secara aman.')
  } catch (error) {
    const detail = error.response?.data
    errorMessage.value = detail?.password?.[0] || detail?.username?.[0] || detail?.detail || 'Gagal membuat user.'
  } finally {
    isCreating.value = false
  }
}

async function handleRoleChange(user, roleId) {
  try {
    await updateUser(user.id, { role: roleId || null })
    await fetchAll()
  } catch {
    errorMessage.value = 'Gagal mengubah role.'
  }
}

function askToggleActive(user) {
  confirmState.open = true
  confirmState.user = user
  confirmState.action = user.is_active ? 'deactivate' : 'activate'
}

function askDelete(user) {
  confirmState.open = true
  confirmState.user = user
  confirmState.action = 'delete'
}

async function confirmToggleActive() {
  confirmState.open = false
  const { user, action } = confirmState
  try {
    if (action === 'delete') {
      await deleteUser(user.id)
    } else if (action === 'deactivate') {
      await deactivateUser(user.id)
    } else {
      await activateUser(user.id)
    }
    await fetchAll()
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || 'Aksi gagal dilakukan.'
  }
}

function askResetPassword(user) {
  resetState.open = true
  resetState.user = user
  resetState.newPassword = ''
}

async function confirmResetPassword() {
  try {
    await resetUserPassword(resetState.user.id, resetState.newPassword)
    resetState.open = false
    showStatus('success', 'Password berhasil direset', `Password baru untuk ${resetState.user.username} sudah aktif.`)
  } catch (error) {
    errorMessage.value = error.response?.data?.new_password?.[0] || 'Gagal reset password (minimal 8 karakter, tidak boleh terlalu umum).'
  }
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold text-slate-800">Users</h1>

    <div class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
      <h2 class="text-sm font-semibold text-slate-700">Tambah User</h2>
      <form class="mt-3 flex flex-wrap items-end gap-3" @submit.prevent="handleCreate">
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Username</label>
          <input v-model="form.username" required type="text" class="w-40 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Email</label>
          <input v-model="form.email" required type="email" class="w-52 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Password Awal</label>
          <input v-model="form.password" required type="text" class="w-44 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Role</label>
          <select v-model="form.role" class="w-40 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500">
            <option value="">Tanpa Role</option>
            <option v-for="role in roles" :key="role.id" :value="role.id">{{ role.name }}</option>
          </select>
        </div>
        <button type="submit" :disabled="isCreating" class="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60">
          {{ isCreating ? 'Membuat...' : 'Buat User' }}
        </button>
      </form>
      <p v-if="errorMessage" class="mt-3 text-sm text-red-600">{{ errorMessage }}</p>
    </div>

    <div class="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th class="px-4 py-3">Username</th>
            <th class="px-4 py-3">Email</th>
            <th class="px-4 py-3">Role</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Last Login</th>
            <th class="px-4 py-3 text-right">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-if="isLoading">
            <td colspan="6" class="px-4 py-8 text-center text-slate-400">Memuat data...</td>
          </tr>
          <tr v-for="u in users" v-else :key="u.id" class="hover:bg-slate-50">
            <td class="px-4 py-3 font-medium text-slate-700">
              {{ u.username }} <span v-if="u.is_superuser" class="ml-1 text-xs text-brand-600">(superuser)</span>
            </td>
            <td class="px-4 py-3 text-slate-500">{{ u.email }}</td>
            <td class="px-4 py-3">
              <select
                :value="u.role?.id || ''"
                :disabled="u.is_superuser"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
                @change="handleRoleChange(u, $event.target.value)"
              >
                <option value="">Tanpa Role</option>
                <option v-for="role in roles" :key="role.id" :value="role.id">{{ role.name }}</option>
              </select>
            </td>
            <td class="px-4 py-3">
              <span class="rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="u.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'">
                {{ u.is_active ? 'Aktif' : 'Nonaktif' }}
              </span>
            </td>
            <td class="px-4 py-3 text-slate-500">{{ u.last_login ? new Date(u.last_login).toLocaleString() : 'Belum pernah' }}</td>
            <td class="px-4 py-3 text-right">
              <div class="flex justify-end gap-2">
                <button
                  class="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
                  @click="askResetPassword(u)"
                >
                  Reset Password
                </button>
                <button
                  v-if="u.id !== auth.user?.id"
                  class="rounded-md border px-2.5 py-1 text-xs font-medium"
                  :class="u.is_active ? 'border-amber-300 text-amber-700 hover:bg-amber-50' : 'border-emerald-300 text-emerald-700 hover:bg-emerald-50'"
                  @click="askToggleActive(u)"
                >
                  {{ u.is_active ? 'Nonaktifkan' : 'Aktifkan' }}
                </button>
                <button
                  v-if="u.id !== auth.user?.id && !u.is_superuser"
                  class="rounded-md bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700"
                  @click="askDelete(u)"
                >
                  Hapus
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ConfirmDialog
      :open="confirmState.open"
      :title="{
        delete: 'Hapus user?',
        deactivate: 'Nonaktifkan user?',
        activate: 'Aktifkan kembali user?',
      }[confirmState.action]"
      :message="
        confirmState.action === 'delete'
          ? `${confirmState.user?.username} akan dihapus permanen. Riwayat aktivitasnya (audit log, alert, dll) tetap tersimpan tapi tidak lagi terhubung ke akun ini.`
          : `${confirmState.user?.username} akan di-${confirmState.action === 'deactivate' ? 'nonaktifkan' : 'aktifkan kembali'}.`
      "
      :confirm-label="{ delete: 'Hapus', deactivate: 'Nonaktifkan', activate: 'Aktifkan' }[confirmState.action]"
      :danger="confirmState.action === 'delete' || confirmState.action === 'deactivate'"
      @confirm="confirmToggleActive"
      @cancel="confirmState.open = false"
    />

    <div v-if="resetState.open" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" @click.self="resetState.open = false">
      <div class="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
        <h2 class="text-base font-semibold text-slate-800">Reset password: {{ resetState.user?.username }}</h2>
        <input
          v-model="resetState.newPassword"
          type="text"
          placeholder="Password baru"
          class="mt-4 w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <div class="mt-5 flex justify-end gap-2">
          <button class="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50" @click="resetState.open = false">Batal</button>
          <button
            class="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            :disabled="resetState.newPassword.length < 8"
            @click="confirmResetPassword"
          >
            Reset
          </button>
        </div>
      </div>
    </div>

    <StatusModal
      :open="status.open"
      :variant="status.variant"
      :title="status.title"
      :message="status.message"
      :auto-close-ms="2500"
      @primary="status.open = false"
      @close="status.open = false"
    />
  </div>
</template>
