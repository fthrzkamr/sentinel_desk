<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { createEnrollmentToken, listEnrollmentTokens, revokeEnrollmentToken } from '@/services/devices'
import {
  createBranch,
  createCompany,
  createDepartment,
  createEmployee,
  deleteBranch,
  deleteCompany,
  deleteDepartment,
  deleteEmployee,
  listBranches,
  listCompanies,
  listDepartments,
  listEmployees,
} from '@/services/organization'

const tokens = ref([])
const isLoading = ref(true)
const errorMessage = ref('')

const form = reactive({
  label: '',
  ttl_minutes: 60,
  company: '',
  branch: '',
  department: '',
  assigned_employee: '',
})
const isCreating = ref(false)
const revealedToken = ref(null)
const copyLabel = ref('Copy')

const confirmState = reactive({ open: false, token: null })

// --- Enrollment tokens ---

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
      company: form.company || null,
      branch: form.branch || null,
      department: form.department || null,
      assigned_employee: form.assigned_employee || null,
    })
    revealedToken.value = data
    form.label = ''
    form.company = ''
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

// company/branch/department are each already the full "Company / Branch /
// Department" chain (see their __str__ on the backend) — only the deepest
// non-empty one is needed, joining all four like the old code did just
// duplicated every ancestor's name once per descendant level.
function assignPath(token) {
  const orgChain = token.department || token.branch || token.company || ''
  return [orgChain, token.assigned_employee].filter(Boolean).join(' / ') || '-'
}

// --- Org structure: cascading pickers for the token form ---

const companies = ref([])
const branches = ref([])
const departments = ref([])
const employees = ref([])

async function fetchCompanies() {
  const { data } = await listCompanies({ page_size: 200 })
  companies.value = data.results
}

watch(
  () => form.company,
  async (companyId) => {
    form.branch = ''
    branches.value = []
    if (!companyId) return
    const { data } = await listBranches({ company: companyId, page_size: 200 })
    branches.value = data.results
  },
)

watch(
  () => form.branch,
  async (branchId) => {
    form.department = ''
    departments.value = []
    if (!branchId) return
    const { data } = await listDepartments({ branch: branchId, page_size: 200 })
    departments.value = data.results
  },
)

watch(
  () => form.department,
  async (departmentId) => {
    form.assigned_employee = ''
    employees.value = []
    if (!departmentId) return
    const { data } = await listEmployees({ department: departmentId, page_size: 200 })
    employees.value = data.results
  },
)

onMounted(async () => {
  await fetchCompanies()
  await fetchPanelBranches()
  await fetchPanelDepartments()
})

// --- Org structure management panel ---

const showOrgPanel = ref(false)
const orgError = ref('')

const newCompanyName = ref('')
const newBranch = reactive({ company: '', name: '' })
const newDepartment = reactive({ branch: '', name: '' })
const newEmployee = reactive({ department: '', full_name: '', email: '', position: '' })

// Flat, unfiltered — each card's own "pick the parent" dropdown needs every
// branch/department that exists regardless of what's picked elsewhere on
// the panel (a plain <select> handles dozens of options fine). The
// *displayed list* below each dropdown is a different story — with real
// data (20 branches, 88 departments) dumping all of them unfiltered turned
// into an unreadable wall of repeated names, so those lists are filtered
// down to just the currently-selected parent instead (see the filtered*
// computed properties).
const panelBranches = ref([])
const panelDepartments = ref([])
const panelEmployees = ref([])

const filteredPanelBranches = computed(() =>
  newBranch.company ? panelBranches.value.filter((b) => b.company === newBranch.company) : [],
)
const filteredPanelDepartments = computed(() =>
  newDepartment.branch ? panelDepartments.value.filter((d) => d.branch === newDepartment.branch) : [],
)

async function fetchPanelBranches() {
  const { data } = await listBranches({ page_size: 200 })
  panelBranches.value = data.results
}

async function fetchPanelDepartments() {
  const { data } = await listDepartments({ page_size: 200 })
  panelDepartments.value = data.results
}

async function fetchPanelEmployees() {
  if (!newEmployee.department) {
    panelEmployees.value = []
    return
  }
  const { data } = await listEmployees({ department: newEmployee.department, page_size: 200 })
  panelEmployees.value = data.results
}

watch(() => newEmployee.department, fetchPanelEmployees)

async function refreshOrgLists() {
  await Promise.all([fetchCompanies(), fetchPanelBranches(), fetchPanelDepartments(), fetchPanelEmployees()])
}

async function handleAddCompany() {
  if (!newCompanyName.value.trim()) return
  orgError.value = ''
  try {
    await createCompany({ name: newCompanyName.value.trim() })
    newCompanyName.value = ''
    await refreshOrgLists()
  } catch (error) {
    orgError.value = error.response?.data?.name?.[0] || 'Gagal menambah company.'
  }
}

async function handleAddBranch() {
  if (!newBranch.company || !newBranch.name.trim()) return
  orgError.value = ''
  try {
    await createBranch({ company: newBranch.company, name: newBranch.name.trim() })
    newBranch.name = ''
    await refreshOrgLists()
  } catch (error) {
    orgError.value = error.response?.data?.name?.[0] || error.response?.data?.non_field_errors?.[0] || 'Gagal menambah branch.'
  }
}

async function handleAddDepartment() {
  if (!newDepartment.branch || !newDepartment.name.trim()) return
  orgError.value = ''
  try {
    await createDepartment({ branch: newDepartment.branch, name: newDepartment.name.trim() })
    newDepartment.name = ''
    await refreshOrgLists()
  } catch (error) {
    orgError.value = error.response?.data?.name?.[0] || 'Gagal menambah department.'
  }
}

async function handleAddEmployee() {
  if (!newEmployee.department || !newEmployee.full_name.trim()) return
  orgError.value = ''
  try {
    await createEmployee({
      department: newEmployee.department,
      full_name: newEmployee.full_name.trim(),
      email: newEmployee.email.trim(),
      position: newEmployee.position.trim(),
    })
    newEmployee.full_name = ''
    newEmployee.email = ''
    newEmployee.position = ''
    await fetchPanelEmployees()
  } catch (error) {
    orgError.value = error.response?.data?.full_name?.[0] || 'Gagal menambah karyawan.'
  }
}

// --- Delete (company/branch deletion cascades to what's under it; an
// employee losing its department just clears that link, it's never deleted
// as a side effect) ---

const deleteConfirm = reactive({ open: false, type: '', id: null, label: '', warning: '' })

function askDeleteCompany(company) {
  Object.assign(deleteConfirm, {
    open: true,
    type: 'company',
    id: company.id,
    label: company.name,
    warning: 'Semua Branch dan Department di bawahnya ikut terhapus. Karyawan tidak ikut terhapus, hanya kehilangan assignment-nya.',
  })
}

function askDeleteBranch(branch) {
  Object.assign(deleteConfirm, {
    open: true,
    type: 'branch',
    id: branch.id,
    label: branch.name,
    warning: 'Semua Department di bawahnya ikut terhapus. Karyawan tidak ikut terhapus, hanya kehilangan assignment-nya.',
  })
}

function askDeleteDepartment(department) {
  Object.assign(deleteConfirm, {
    open: true,
    type: 'department',
    id: department.id,
    label: department.name,
    warning: 'Karyawan di department ini tidak ikut terhapus, hanya kehilangan assignment-nya.',
  })
}

function askDeleteEmployee(employee) {
  Object.assign(deleteConfirm, {
    open: true,
    type: 'employee',
    id: employee.id,
    label: employee.full_name,
    warning: '',
  })
}

async function confirmDelete() {
  deleteConfirm.open = false
  orgError.value = ''
  try {
    if (deleteConfirm.type === 'company') await deleteCompany(deleteConfirm.id)
    else if (deleteConfirm.type === 'branch') await deleteBranch(deleteConfirm.id)
    else if (deleteConfirm.type === 'department') await deleteDepartment(deleteConfirm.id)
    else if (deleteConfirm.type === 'employee') await deleteEmployee(deleteConfirm.id)
    await refreshOrgLists()
  } catch (error) {
    orgError.value = error.response?.data?.detail || 'Gagal menghapus.'
  }
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
            class="w-44 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Berlaku (menit)</label>
          <input
            v-model.number="form.ttl_minutes"
            type="number"
            min="1"
            max="10080"
            class="w-24 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>
        <button
          type="submit"
          :disabled="isCreating"
          class="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {{ isCreating ? 'Membuat...' : 'Buat Token' }}
        </button>
        <button
          type="button"
          class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
          @click="showOrgPanel = !showOrgPanel"
        >
          {{ showOrgPanel ? 'Tutup kelola organisasi' : 'Kelola Company/Branch/Dept/Karyawan' }}
        </button>
      </form>

      <div class="mt-3 grid grid-cols-2 gap-3 border-t border-slate-100 pt-3 sm:grid-cols-4">
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Company (opsional)</label>
          <select v-model="form.company" class="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
            <option value="">Tidak diisi</option>
            <option v-for="c in companies" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Branch</label>
          <select
            v-model="form.branch"
            :disabled="!form.company"
            class="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-50 disabled:text-slate-400"
          >
            <option value="">Tidak diisi</option>
            <option v-for="b in branches" :key="b.id" :value="b.id">{{ b.name }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Department</label>
          <select
            v-model="form.department"
            :disabled="!form.branch"
            class="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-50 disabled:text-slate-400"
          >
            <option value="">Tidak diisi</option>
            <option v-for="d in departments" :key="d.id" :value="d.id">{{ d.name }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Karyawan</label>
          <select
            v-model="form.assigned_employee"
            :disabled="!form.department"
            class="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-50 disabled:text-slate-400"
          >
            <option value="">Tidak diisi</option>
            <option v-for="e in employees" :key="e.id" :value="e.id">{{ e.full_name }}</option>
          </select>
        </div>
      </div>
      <p class="mt-1.5 text-xs text-slate-400">
        Kalau diisi, device yang enroll pakai token ini otomatis ter-assign ke pilihan di atas — tidak perlu
        diatur manual lagi setelahnya.
      </p>

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

    <div v-if="showOrgPanel" class="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
      <h2 class="text-sm font-semibold text-slate-700">Kelola Struktur Organisasi</h2>
      <p class="mt-1 text-xs text-slate-500">
        Buat Company dulu, baru Branch di bawahnya, baru Department, baru Karyawan — sesuai urutan.
      </p>

      <div class="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-4">
        <div class="space-y-2 rounded-lg border border-slate-100 p-3">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Company <span class="font-normal normal-case text-slate-400">({{ companies.length }})</span>
          </h3>
          <form class="flex gap-1.5" @submit.prevent="handleAddCompany">
            <input
              v-model="newCompanyName"
              type="text"
              placeholder="Nama company"
              class="w-full rounded-md border border-slate-300 px-2 py-1 text-xs"
            />
            <button type="submit" class="shrink-0 rounded-md bg-brand-600 px-2 py-1 text-xs text-white hover:bg-brand-700">
              Tambah
            </button>
          </form>
          <ul class="max-h-48 space-y-1 overflow-y-auto text-xs text-slate-600">
            <li v-for="c in companies" :key="c.id" class="flex items-center justify-between rounded bg-slate-50 px-2 py-1">
              <span>{{ c.name }}</span>
              <button class="text-slate-400 hover:text-red-600" title="Hapus" @click="askDeleteCompany(c)">✕</button>
            </li>
            <li v-if="companies.length === 0" class="text-slate-400">Belum ada.</li>
          </ul>
        </div>

        <div class="space-y-2 rounded-lg border border-slate-100 p-3">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Branch <span class="font-normal normal-case text-slate-400">({{ panelBranches.length }} total)</span>
          </h3>
          <select v-model="newBranch.company" class="w-full rounded-md border border-slate-300 px-2 py-1 text-xs">
            <option value="">Pilih company...</option>
            <option v-for="c in companies" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
          <form class="flex gap-1.5" @submit.prevent="handleAddBranch">
            <input
              v-model="newBranch.name"
              type="text"
              placeholder="Nama branch"
              :disabled="!newBranch.company"
              class="w-full rounded-md border border-slate-300 px-2 py-1 text-xs disabled:bg-slate-50"
            />
            <button
              type="submit"
              :disabled="!newBranch.company"
              class="shrink-0 rounded-md bg-brand-600 px-2 py-1 text-xs text-white hover:bg-brand-700 disabled:opacity-50"
            >
              Tambah
            </button>
          </form>
          <ul class="max-h-48 space-y-1 overflow-y-auto text-xs text-slate-600">
            <li
              v-for="b in filteredPanelBranches"
              :key="b.id"
              class="flex items-center justify-between rounded bg-slate-50 px-2 py-1"
            >
              <span>{{ b.name }}</span>
              <button class="text-slate-400 hover:text-red-600" title="Hapus" @click="askDeleteBranch(b)">✕</button>
            </li>
            <li v-if="newBranch.company && filteredPanelBranches.length === 0" class="text-slate-400">Belum ada.</li>
            <li v-if="!newBranch.company" class="text-slate-400">Pilih company untuk lihat branch-nya.</li>
          </ul>
        </div>

        <div class="space-y-2 rounded-lg border border-slate-100 p-3">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Department <span class="font-normal normal-case text-slate-400">({{ panelDepartments.length }} total)</span>
          </h3>
          <select v-model="newDepartment.branch" class="w-full rounded-md border border-slate-300 px-2 py-1 text-xs">
            <option value="">Pilih branch...</option>
            <option v-for="b in panelBranches" :key="b.id" :value="b.id">{{ b.company_name }} / {{ b.name }}</option>
          </select>
          <form class="flex gap-1.5" @submit.prevent="handleAddDepartment">
            <input
              v-model="newDepartment.name"
              type="text"
              placeholder="Nama department"
              :disabled="!newDepartment.branch"
              class="w-full rounded-md border border-slate-300 px-2 py-1 text-xs disabled:bg-slate-50"
            />
            <button
              type="submit"
              :disabled="!newDepartment.branch"
              class="shrink-0 rounded-md bg-brand-600 px-2 py-1 text-xs text-white hover:bg-brand-700 disabled:opacity-50"
            >
              Tambah
            </button>
          </form>
          <ul class="max-h-48 space-y-1 overflow-y-auto text-xs text-slate-600">
            <li
              v-for="d in filteredPanelDepartments"
              :key="d.id"
              class="flex items-center justify-between rounded bg-slate-50 px-2 py-1"
            >
              <span>{{ d.name }}</span>
              <button class="text-slate-400 hover:text-red-600" title="Hapus" @click="askDeleteDepartment(d)">✕</button>
            </li>
            <li v-if="newDepartment.branch && filteredPanelDepartments.length === 0" class="text-slate-400">Belum ada.</li>
            <li v-if="!newDepartment.branch" class="text-slate-400">Pilih branch untuk lihat department-nya.</li>
          </ul>
        </div>

        <div class="space-y-2 rounded-lg border border-slate-100 p-3">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500">Karyawan</h3>
          <select v-model="newEmployee.department" class="w-full rounded-md border border-slate-300 px-2 py-1 text-xs">
            <option value="">Pilih department...</option>
            <option v-for="d in panelDepartments" :key="d.id" :value="d.id">{{ d.branch_label }} / {{ d.name }}</option>
          </select>
          <form class="space-y-1.5" @submit.prevent="handleAddEmployee">
            <input
              v-model="newEmployee.full_name"
              type="text"
              placeholder="Nama lengkap"
              :disabled="!newEmployee.department"
              class="w-full rounded-md border border-slate-300 px-2 py-1 text-xs disabled:bg-slate-50"
            />
            <input
              v-model="newEmployee.position"
              type="text"
              placeholder="Posisi (opsional)"
              :disabled="!newEmployee.department"
              class="w-full rounded-md border border-slate-300 px-2 py-1 text-xs disabled:bg-slate-50"
            />
            <button
              type="submit"
              :disabled="!newEmployee.department"
              class="w-full rounded-md bg-brand-600 px-2 py-1 text-xs text-white hover:bg-brand-700 disabled:opacity-50"
            >
              Tambah Karyawan
            </button>
          </form>
          <ul class="max-h-48 space-y-1 overflow-y-auto text-xs text-slate-600">
            <li
              v-for="e in panelEmployees"
              :key="e.id"
              class="flex items-center justify-between rounded bg-slate-50 px-2 py-1"
            >
              <span>{{ e.full_name }}</span>
              <button class="text-slate-400 hover:text-red-600" title="Hapus" @click="askDeleteEmployee(e)">✕</button>
            </li>
            <li v-if="newEmployee.department && panelEmployees.length === 0" class="text-slate-400">Belum ada.</li>
            <li v-if="!newEmployee.department" class="text-slate-400">Pilih department untuk lihat karyawannya.</li>
          </ul>
        </div>
      </div>

      <p v-if="orgError" class="mt-3 text-sm text-red-600">{{ orgError }}</p>
    </div>

    <ConfirmDialog
      :open="deleteConfirm.open"
      :title="`Hapus ${deleteConfirm.label}?`"
      :message="deleteConfirm.warning || 'Tindakan ini tidak bisa dibatalkan.'"
      confirm-label="Hapus"
      danger
      @confirm="confirmDelete"
      @cancel="deleteConfirm.open = false"
    />

    <div class="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th class="px-4 py-3">Prefix</th>
            <th class="px-4 py-3">Label</th>
            <th class="px-4 py-3">Assign</th>
            <th class="px-4 py-3">Dibuat oleh</th>
            <th class="px-4 py-3">Kedaluwarsa</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Device</th>
            <th class="px-4 py-3 text-right">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-if="isLoading">
            <td colspan="8" class="px-4 py-8 text-center text-slate-400">Memuat data...</td>
          </tr>
          <tr v-else-if="tokens.length === 0">
            <td colspan="8" class="px-4 py-8 text-center text-slate-400">Belum ada enrollment token.</td>
          </tr>
          <tr v-for="token in tokens" v-else :key="token.id" class="hover:bg-slate-50">
            <td class="px-4 py-3 font-mono text-xs">{{ token.token_prefix }}...</td>
            <td class="px-4 py-3">{{ token.label || '-' }}</td>
            <td class="px-4 py-3 text-xs text-slate-500">
              {{ assignPath(token) }}
            </td>
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
                class="rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
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
