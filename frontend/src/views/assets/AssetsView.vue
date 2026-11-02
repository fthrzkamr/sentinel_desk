<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

import Pagination from '@/components/Pagination.vue'
import api from '@/services/api'
import { linkAsset, listAssets, listDevices, setAssetUser } from '@/services/devices'
import { listEmployees } from '@/services/organization'
import { useAuthStore } from '@/stores/auth'
import { downloadCsv } from '@/utils/csv'

const PAGE_SIZE = 25

const auth = useAuthStore()

const rows = ref([])
const isLoading = ref(true)
const isExporting = ref(false)
const errorMessage = ref('')
const search = ref('')
const matchStatusFilter = ref('')
const pageCount = ref(0)
const currentPage = ref(1)
const nextUrl = ref(null)
const previousUrl = ref(null)
const currentUrl = ref(null)

const MATCH_STATUS_OPTIONS = ['AUTO_MATCHED', 'NEEDS_REVIEW', 'LINKED_MANUALLY', 'UNLINKED']
const MATCH_STATUS_LABEL = {
  AUTO_MATCHED: 'Auto-matched',
  NEEDS_REVIEW: 'Perlu Dicocokkan',
  LINKED_MANUALLY: 'Ditautkan Manual',
  UNLINKED: 'Belum Tertaut',
}
const MATCH_STATUS_STYLE = {
  AUTO_MATCHED: 'bg-emerald-100 text-emerald-700',
  NEEDS_REVIEW: 'bg-amber-100 text-amber-700',
  LINKED_MANUALLY: 'bg-sky-100 text-sky-700',
  UNLINKED: 'bg-slate-200 text-slate-600',
}

async function fetchAssets(url = null) {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = url
      ? await api.get(url, { baseURL: '' })
      : await listAssets({
          search: search.value || undefined,
          match_status: matchStatusFilter.value || undefined,
        })
    rows.value = data.results
    pageCount.value = data.count
    nextUrl.value = data.next
    previousUrl.value = data.previous
    currentUrl.value = url
  } catch {
    errorMessage.value = 'Gagal memuat data asset.'
  } finally {
    isLoading.value = false
  }
}

function goNext() {
  if (!nextUrl.value) return
  currentPage.value += 1
  fetchAssets(nextUrl.value)
}

function goPrevious() {
  if (!previousUrl.value) return
  currentPage.value -= 1
  fetchAssets(previousUrl.value)
}

async function exportCsv() {
  isExporting.value = true
  try {
    const { data } = await listAssets({
      search: search.value || undefined,
      match_status: matchStatusFilter.value || undefined,
      page_size: 500,
    })
    downloadCsv('assets.csv', data.results || [], [
      { header: 'Kode Asset', value: (r) => r.asset_code },
      { header: 'Nama Aset', value: (r) => r.nama_aset || '' },
      { header: 'Merk', value: (r) => r.merk || '' },
      { header: 'Spesifikasi', value: (r) => r.spesifikasi || '' },
      { header: 'Pengguna Saat Ini', value: (r) => r.current_employee || '' },
      { header: 'Penanggung Jawab (asset_dfm)', value: (r) => r.raw_penanggung_jawab || '' },
      { header: 'Lokasi (asset_dfm)', value: (r) => r.raw_lokasi || '' },
      { header: 'Kondisi', value: (r) => r.kondisi || '' },
      { header: 'Status Barang', value: (r) => r.status_barang || '' },
      { header: 'Device ID Tertaut', value: (r) => r.device_id || '' },
      { header: 'Hostname Device', value: (r) => r.device_hostname || '' },
      { header: 'Status Match', value: (r) => MATCH_STATUS_LABEL[r.match_status] || r.match_status },
    ])
  } finally {
    isExporting.value = false
  }
}

let searchDebounce = null
watch([search, matchStatusFilter], () => {
  clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => {
    currentPage.value = 1
    fetchAssets()
  }, 300)
})

onMounted(fetchAssets)

// --- Manual link (for NEEDS_REVIEW / UNLINKED / fixing a wrong match) ---

const allDevices = ref([])
async function fetchAllDevices() {
  // Picking a device to link is a one-time, occasional admin action, not a
  // frequent lookup — a flat page_size covers this fleet's realistic size
  // without needing a searchable combobox component just for this dropdown.
  const { data } = await listDevices({ page_size: 500 })
  allDevices.value = data.results
}

const linkState = reactive({ open: false, asset: null, deviceId: '', isSaving: false, error: '' })

// Quick-accept the matcher's own suggestion (see suggested_device on the
// backend) — same linkAsset() call startLink()/confirmLink() use below,
// just skipping the modal since there's nothing left to pick.
const confirmingId = ref(null)
async function confirmSuggestion(asset) {
  confirmingId.value = asset.id
  try {
    await linkAsset(asset.id, asset.suggested_device_id)
    await fetchAssets(currentUrl.value)
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || 'Gagal konfirmasi tautan asset.'
  } finally {
    confirmingId.value = null
  }
}

// --- Set current user (the simple, always-available "who's using this"
// field — independent of device-linking above, see Asset.current_employee
// on the backend) ---

const allEmployees = ref([])
async function fetchAllEmployees() {
  const { data } = await listEmployees({ page_size: 500 })
  allEmployees.value = data.results
}

const userState = reactive({ open: false, asset: null, employeeId: '', isSaving: false, error: '' })

// Plain <select> gets unusable once the employee list grows past a
// screenful — unlike the device-link dropdown above (small, occasional),
// this one gets used repeatedly while bulk-processing "Data Belum
// Lengkap"/"nama ada, belum terdaftar" rows, so it's worth a real
// type-to-filter box instead.
const employeeSearch = ref('')
const employeeDropdownOpen = ref(false)
const filteredEmployees = computed(() => {
  const q = employeeSearch.value.trim().toLowerCase()
  const pool = q ? allEmployees.value.filter((e) => e.full_name.toLowerCase().includes(q)) : allEmployees.value
  return pool.slice(0, 50)
})

function selectEmployee(employee) {
  userState.employeeId = employee ? employee.id : ''
  employeeSearch.value = employee ? employee.full_name : ''
  employeeDropdownOpen.value = false
}

function startSetUser(asset) {
  userState.open = true
  userState.asset = asset
  userState.employeeId = asset.current_employee_id || ''
  employeeSearch.value = asset.current_employee || ''
  employeeDropdownOpen.value = false
  userState.error = ''
  if (allEmployees.value.length === 0) fetchAllEmployees()
}

async function confirmSetUser() {
  userState.isSaving = true
  userState.error = ''
  try {
    await setAssetUser(userState.asset.id, userState.employeeId || null)
    userState.open = false
    await fetchAssets(currentUrl.value)
  } catch (error) {
    userState.error = error.response?.data?.detail || 'Gagal menyimpan pengguna asset.'
  } finally {
    userState.isSaving = false
  }
}

// --- View details (plain display mirror of asset_dfm's name/brand/specs/
// detailed location - see Asset model docstring. Needs no extra API call,
// the list endpoint already includes these fields on every row) ---

const viewState = reactive({ open: false, asset: null })

function openView(asset) {
  viewState.open = true
  viewState.asset = asset
}

function startLink(asset) {
  linkState.open = true
  linkState.asset = asset
  linkState.deviceId = asset.device_id || ''
  linkState.error = ''
  if (allDevices.value.length === 0) fetchAllDevices()
}

async function confirmLink() {
  linkState.isSaving = true
  linkState.error = ''
  try {
    await linkAsset(linkState.asset.id, linkState.deviceId || null)
    linkState.open = false
    await fetchAssets(currentUrl.value)
  } catch (error) {
    linkState.error = error.response?.data?.detail || 'Gagal menautkan asset.'
  } finally {
    linkState.isSaving = false
  }
}

// Quick one-click unlink — same end result as "Ubah Link" -> "Tidak
// ditautkan" -> Simpan, just without opening the modal for the common
// "oops, wrong pick" case.
const unlinkingId = ref(null)
async function unlinkAsset(asset) {
  unlinkingId.value = asset.id
  errorMessage.value = ''
  try {
    await linkAsset(asset.id, null)
    await fetchAssets(currentUrl.value)
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || 'Gagal melepas tautan asset.'
  } finally {
    unlinkingId.value = null
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold text-slate-800">Assets</h1>
        <p class="mt-1 text-sm text-slate-500">
          Disinkronkan otomatis dari sistem asset_dfm, lalu dicocokkan ke device SentinelDesk berdasarkan
          nama penanggung jawab & cabang. Yang berstatus "Perlu Dicocokkan" butuh konfirmasi manual sekali.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <input
          v-model="search"
          type="text"
          placeholder="Cari kode asset..."
          class="w-56 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <select
          v-model="matchStatusFilter"
          class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">Semua Status</option>
          <option v-for="opt in MATCH_STATUS_OPTIONS" :key="opt" :value="opt">{{ MATCH_STATUS_LABEL[opt] }}</option>
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

    <div class="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th class="px-4 py-3">Kode Asset</th>
            <th class="px-4 py-3">Pengguna</th>
            <th class="px-4 py-3">Kondisi</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Device Tertaut</th>
            <th class="px-4 py-3">Match</th>
            <th class="px-4 py-3 text-right">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100" :class="{ 'opacity-50 transition-opacity': isLoading && rows.length > 0 }">
          <tr v-if="isLoading && rows.length === 0">
            <td colspan="7" class="px-4 py-8 text-center text-slate-400">Memuat data...</td>
          </tr>
          <tr v-else-if="errorMessage">
            <td colspan="7" class="px-4 py-8 text-center text-red-500">{{ errorMessage }}</td>
          </tr>
          <tr v-else-if="rows.length === 0">
            <td colspan="7" class="px-4 py-8 text-center text-slate-400">
              Belum ada asset yang ter-sync. Data masuk otomatis begitu asset_dfm memanggil
              <code>POST /api/assets/sync/</code>.
            </td>
          </tr>
          <tr v-for="asset in rows" v-else :key="asset.id" class="hover:bg-slate-50">
            <td class="px-4 py-3 font-mono text-xs">{{ asset.asset_code }}</td>
            <td class="px-4 py-3">
              <button
                v-if="auth.hasPermission('device.manage')"
                class="text-left hover:underline"
                :class="asset.current_employee ? 'font-medium text-slate-700' : 'text-slate-400'"
                @click="startSetUser(asset)"
              >
                <template v-if="asset.current_employee">{{ asset.current_employee }}</template>
                <template v-else-if="asset.user_status === 'INCOMPLETE'">
                  <span class="rounded-full bg-slate-200 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                    Data Belum Lengkap
                  </span>
                </template>
                <template v-else-if="asset.user_status === 'NEEDS_EMPLOYEE'">
                  <span class="text-amber-700">"{{ asset.raw_penanggung_jawab }}"</span>
                  <span class="block text-[11px] text-slate-400">nama ada, belum terdaftar — klik untuk pilih/tambah</span>
                </template>
                <template v-else>Belum diatur — klik untuk isi</template>
              </button>
              <template v-else>
                <span v-if="asset.current_employee" class="font-medium text-slate-700">{{ asset.current_employee }}</span>
                <span v-else-if="asset.user_status === 'INCOMPLETE'" class="rounded-full bg-slate-200 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                  Data Belum Lengkap
                </span>
                <span v-else class="text-slate-400">{{ asset.raw_penanggung_jawab || 'Belum diatur' }}</span>
              </template>
            </td>
            <td class="px-4 py-3">{{ asset.kondisi }}</td>
            <td class="px-4 py-3">{{ asset.status_barang }}</td>
            <td class="px-4 py-3">
              <div v-if="asset.device_id">
                <div class="font-medium text-slate-700">{{ asset.device_hostname }}</div>
                <div class="text-xs text-slate-400">{{ asset.assigned_employee || '-' }} &middot; {{ asset.branch || '-' }}</div>
              </div>
              <div v-else-if="asset.suggested_employee">
                <div class="font-medium text-amber-700">Mungkin: {{ asset.suggested_employee }}</div>
                <div class="text-xs text-slate-400">{{ asset.suggested_device_hostname }}</div>
                <div class="mt-0.5 text-[11px] text-slate-400">
                  Dari asset_dfm: "{{ asset.raw_penanggung_jawab || '-' }}" / {{ asset.raw_lokasi || '-' }}
                </div>
              </div>
              <div v-else class="text-xs text-slate-400">
                Dari asset_dfm: "{{ asset.raw_penanggung_jawab || '-' }}" / {{ asset.raw_lokasi || '-' }}
              </div>
            </td>
            <td class="px-4 py-3 text-center">
              <span
                class="text-base font-bold"
                :class="asset.device_id ? 'text-emerald-600' : 'text-rose-500'"
                :title="MATCH_STATUS_LABEL[asset.match_status] + (asset.match_confidence !== null ? ` (confidence ${Math.round(asset.match_confidence * 100)}%)` : '')"
              >{{ asset.device_id ? '✓' : '✗' }}</span>
            </td>
            <td class="px-4 py-3 text-right">
              <div class="flex justify-end gap-1.5">
                <button
                  class="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
                  @click="openView(asset)"
                >
                  View
                </button>
                <button
                  v-if="auth.hasPermission('device.manage') && !asset.device_id && asset.suggested_device_id"
                  class="rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700"
                  :disabled="confirmingId === asset.id"
                  @click="confirmSuggestion(asset)"
                >
                  Konfirmasi
                </button>
                <button
                  v-if="auth.hasPermission('device.manage')"
                  class="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
                  @click="startLink(asset)"
                >
                  {{ asset.device_id ? 'Ubah Link' : 'Tautkan Lain' }}
                </button>
                <button
                  v-if="auth.hasPermission('device.manage') && asset.device_id"
                  class="rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
                  :disabled="unlinkingId === asset.id"
                  @click="unlinkAsset(asset)"
                >
                  Lepas Tautan
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <Pagination
      v-if="rows.length > 0"
      :page="currentPage"
      :page-size="PAGE_SIZE"
      :count="pageCount"
      :has-previous="Boolean(previousUrl)"
      :has-next="Boolean(nextUrl)"
      @previous="goPrevious"
      @next="goNext"
    />

    <div
      v-if="linkState.open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      @click.self="linkState.open = false"
    >
      <div class="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
        <h2 class="text-base font-semibold text-slate-800">Tautkan Asset {{ linkState.asset?.asset_code }}</h2>
        <p class="mt-1 text-xs text-slate-500">
          Dari asset_dfm: "{{ linkState.asset?.raw_penanggung_jawab || '-' }}" / {{ linkState.asset?.raw_lokasi || '-' }}
        </p>
        <select
          v-model="linkState.deviceId"
          class="mt-3 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
        >
          <option value="">Tidak ditautkan</option>
          <option v-for="d in allDevices" :key="d.device_id" :value="d.device_id">
            {{ d.hostname }} &mdash; {{ d.assigned_employee || 'belum ada karyawan' }} ({{ d.device_id }})
          </option>
        </select>
        <p v-if="linkState.error" class="mt-2 text-sm text-red-600">{{ linkState.error }}</p>
        <div class="mt-4 flex justify-end gap-2">
          <button
            class="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            @click="linkState.open = false"
          >
            Batal
          </button>
          <button
            :disabled="linkState.isSaving"
            class="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
            @click="confirmLink"
          >
            {{ linkState.isSaving ? 'Menyimpan...' : 'Simpan' }}
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="userState.open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      @click.self="userState.open = false"
    >
      <div class="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
        <h2 class="text-base font-semibold text-slate-800">Pengguna Asset {{ userState.asset?.asset_code }}</h2>
        <p class="mt-1 text-xs text-slate-500">
          Dari asset_dfm: "{{ userState.asset?.raw_penanggung_jawab || '-' }}" / {{ userState.asset?.raw_lokasi || '-' }}.
          Ini independen dari status link device — berguna kalau laptop sudah pindah tangan ke karyawan lain.
        </p>
        <div class="relative mt-3">
          <input
            v-model="employeeSearch"
            type="text"
            placeholder="Cari nama karyawan..."
            class="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            @focus="employeeDropdownOpen = true"
            @blur="employeeDropdownOpen = false"
          />
          <div
            v-if="employeeDropdownOpen"
            class="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-md border border-slate-200 bg-white shadow-lg"
          >
            <button
              type="button"
              class="block w-full px-3 py-1.5 text-left text-sm text-slate-500 hover:bg-slate-50"
              @mousedown.prevent="selectEmployee(null)"
            >
              Tidak ada
            </button>
            <button
              v-for="e in filteredEmployees"
              :key="e.id"
              type="button"
              class="block w-full px-3 py-1.5 text-left text-sm hover:bg-slate-50"
              :class="{ 'bg-brand-50 font-medium text-brand-700': e.id === userState.employeeId }"
              @mousedown.prevent="selectEmployee(e)"
            >
              <div class="font-medium text-slate-800">{{ e.full_name }}</div>
              <div class="text-xs text-slate-500">{{ e.branch_name || 'Kantor' }} &middot; {{ e.department_name || e.position || 'Staff' }}</div>
            </button>
            <p v-if="filteredEmployees.length === 0" class="px-3 py-1.5 text-sm text-slate-400">Tidak ditemukan</p>
          </div>
        </div>
        <p v-if="userState.error" class="mt-2 text-sm text-red-600">{{ userState.error }}</p>
        <div class="mt-4 flex justify-end gap-2">
          <button
            class="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            @click="userState.open = false"
          >
            Batal
          </button>
          <button
            :disabled="userState.isSaving"
            class="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
            @click="confirmSetUser"
          >
            {{ userState.isSaving ? 'Menyimpan...' : 'Simpan' }}
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="viewState.open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      @click.self="viewState.open = false"
    >
      <div class="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 class="text-base font-semibold text-slate-800">{{ viewState.asset?.asset_code }}</h2>
        <p class="mt-1 text-xs text-slate-500">
          Data dari asset_dfm — dipakai buat nyocokkan ke fisik laptopnya, terutama kalau belum ter-install SentinelDesk.
        </p>
        <dl class="mt-4 space-y-2.5 text-sm">
          <div class="flex justify-between gap-4">
            <dt class="text-slate-500">Nama Aset</dt>
            <dd class="text-right font-medium text-slate-800">{{ viewState.asset?.nama_aset || '-' }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="text-slate-500">Merk</dt>
            <dd class="text-right font-medium text-slate-800">{{ viewState.asset?.merk || '-' }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="shrink-0 text-slate-500">Spesifikasi</dt>
            <dd class="text-right text-slate-800">{{ viewState.asset?.spesifikasi || '-' }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="text-slate-500">Lokasi</dt>
            <dd class="text-right text-slate-800">
              {{ viewState.asset?.raw_lokasi || '-' }}
              <span v-if="viewState.asset?.lokasi_detail">&middot; {{ viewState.asset.lokasi_detail }}</span>
            </dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="text-slate-500">Penanggung Jawab</dt>
            <dd class="text-right text-slate-800">{{ viewState.asset?.raw_penanggung_jawab || '-' }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="text-slate-500">Kondisi / Status</dt>
            <dd class="text-right text-slate-800">{{ viewState.asset?.kondisi }} &middot; {{ viewState.asset?.status_barang }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="text-slate-500">Device SentinelDesk</dt>
            <dd class="text-right text-slate-800">{{ viewState.asset?.device_hostname || 'Belum ter-install' }}</dd>
          </div>
        </dl>
        <div class="mt-5 flex justify-end">
          <button
            class="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            @click="viewState.open = false"
          >
            Tutup
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
