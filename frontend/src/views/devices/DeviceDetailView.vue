<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ConfirmDialog from '@/components/ConfirmDialog.vue'
import LeafletMap from '@/components/LeafletMap.vue'
import LiveScreenPanel from '@/components/LiveScreenPanel.vue'
import MetricTrendChart from '@/components/MetricTrendChart.vue'
import Pagination from '@/components/Pagination.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import UsageBar from '@/components/UsageBar.vue'
import { listAppUsage, listBrowsingHistory, listFileActivity, listIdleActivity, listSystemErrors } from '@/services/activity'
import { getDeviceRiskScore, listAlerts } from '@/services/alerts'
import api from '@/services/api'
import { listAuditLogs } from '@/services/audit'
import { approveDevice, disableDevice, enableDevice, getDevice, rotateDeviceToken, updateDeviceOrgAssignment } from '@/services/devices'
import { getDeviceLocationHistory } from '@/services/locations'
import { getLatestMetric, getMetricHistory } from '@/services/monitoring'
import { listBranches, listCompanies, listDepartments, listEmployees } from '@/services/organization'
import { listSoftware } from '@/services/software'
import { useAuthStore } from '@/stores/auth'
import { useMonitoringStore } from '@/stores/monitoring'
import { downloadCsv } from '@/utils/csv'
import { timeAgo } from '@/utils/time'

const ACTIVITY_PAGE_SIZE = 100

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const monitoring = useMonitoringStore()

const device = ref(null)
const latestMetric = ref(null)
const isLoading = ref(true)
const errorMessage = ref('')
const activeTab = ref('overview')
const confirmOpen = ref(false)

const tabs = computed(() =>
  [
    { key: 'overview', label: 'Overview', available: true },
    { key: 'metrics', label: 'Metrics', available: true },
    { key: 'hardware', label: 'Hardware', available: true },
    { key: 'software', label: 'Software', available: auth.hasPermission('software.view') },
    { key: 'alerts', label: 'Alerts', available: auth.hasPermission('alert.view') },
    { key: 'location', label: 'Location', available: auth.hasPermission('location.view') },
    { key: 'live-screen', label: 'Live Screen', available: auth.hasPermission('monitoring.live_screen') },
    { key: 'app-usage', label: 'App Usage', available: auth.hasPermission('activity.view') },
    { key: 'browsing-history', label: 'Browsing History', available: auth.hasPermission('activity.view') },
    { key: 'file-activity', label: 'File Activity', available: auth.hasPermission('activity.view') },
    { key: 'system-errors', label: 'System Errors', available: auth.hasPermission('activity.view') },
    { key: 'audit', label: 'Audit', available: auth.hasPermission('audit.view') },
  ].filter((tab) => tab.available),
)

const liveMetric = computed(() => monitoring.liveDevices[route.params.deviceId])

const displayStatus = computed(() => liveMetric.value?.status || device.value?.status)
const displayLastSeen = computed(() => liveMetric.value?.last_seen || device.value?.last_seen)

const metric = computed(() => ({
  cpu_percent: liveMetric.value?.cpu_percent ?? latestMetric.value?.cpu_percent ?? null,
  ram_percent: liveMetric.value?.ram_percent ?? latestMetric.value?.ram_percent ?? null,
  disk_percent: liveMetric.value?.disk_percent ?? latestMetric.value?.disk_percent ?? null,
  battery_percent: liveMetric.value?.battery_percent ?? latestMetric.value?.battery_percent ?? null,
  battery_charging: liveMetric.value?.battery_charging ?? latestMetric.value?.battery_charging ?? null,
  net_upload_kbps: latestMetric.value?.net_upload_kbps ?? null,
  net_download_kbps: latestMetric.value?.net_download_kbps ?? null,
  uptime_seconds: latestMetric.value?.uptime_seconds ?? null,
  recorded_at: latestMetric.value?.recorded_at ?? null,
}))

const toggleAction = computed(() => (displayStatus.value === 'DISABLED' ? 'enable' : 'disable'))

function formatUptime(seconds) {
  if (seconds === null || seconds === undefined) return 'Not Available'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

async function fetchDevice() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const { data } = await getDevice(route.params.deviceId)
    device.value = data
  } catch (error) {
    errorMessage.value =
      error.response?.status === 404 ? 'Device tidak ditemukan.' : 'Gagal memuat detail device.'
  } finally {
    isLoading.value = false
  }
}

const riskScore = ref(null)
const isRiskScoreLoading = ref(false)

async function fetchRiskScore() {
  if (!auth.hasPermission('alert.view')) return
  isRiskScoreLoading.value = true
  try {
    const { data } = await getDeviceRiskScore(route.params.deviceId)
    riskScore.value = data
  } catch {
    riskScore.value = null
  } finally {
    isRiskScoreLoading.value = false
  }
}

const RISK_LEVEL_STYLE = {
  HIGH: 'bg-red-50 text-red-600 border-red-200',
  MEDIUM: 'bg-amber-50 text-amber-700 border-amber-200',
  LOW: 'bg-emerald-50 text-emerald-700 border-emerald-200',
}

const ALERT_SEVERITY_STYLE = {
  WARNING: 'bg-amber-100 text-amber-700',
  CRITICAL: 'bg-red-100 text-red-700',
}
const ALERT_STATUS_STYLE = {
  OPEN: 'bg-red-50 text-red-600',
  ACKNOWLEDGED: 'bg-amber-50 text-amber-700',
  RESOLVED: 'bg-emerald-50 text-emerald-700',
}

const RISK_CATEGORY_LABELS = {
  DATA_EXFIL: 'Kemungkinan kebocoran data',
  SUSPICIOUS_URL: 'URL mencurigakan',
  USB: 'Media eksternal (USB)',
  OUT_OF_HOURS: 'Aktivitas di luar jam kerja',
  NEW_SOFTWARE: 'Software baru terdeteksi',
  CONNECTIVITY: 'Konektivitas (offline)',
  CPU: 'CPU tinggi',
  RAM: 'RAM tinggi',
  DISK: 'Disk penuh',
  BATTERY: 'Baterai kritis',
}

const todayIdleStat = ref(null)
const isIdleStatLoading = ref(false)

async function fetchTodayIdleStat() {
  if (!auth.hasPermission('activity.view')) return
  isIdleStatLoading.value = true
  try {
    const today = new Date().toISOString().slice(0, 10)
    const { data } = await listIdleActivity({
      device__device_id: route.params.deviceId,
      date: today,
    })
    todayIdleStat.value = data.results[0] || null
  } catch {
    todayIdleStat.value = null
  } finally {
    isIdleStatLoading.value = false
  }
}

// --- Edit org assignment (Company/Branch/Department/Karyawan) ---

const isEditingOrg = ref(false)
const isSavingOrg = ref(false)
const orgErrorMessage = ref('')
const orgForm = reactive({ company: '', branch: '', department: '', assigned_employee: '' })

const orgCompanies = ref([])
const orgBranches = ref([])
const orgDepartments = ref([])
const orgEmployees = ref([])
const allOrgEmployees = ref([])

async function onOrgEmployeeChange() {
  if (!orgForm.assigned_employee) return
  const selectedEmp = allOrgEmployees.value.find(
    (e) => e.id === Number(orgForm.assigned_employee) || e.id === orgForm.assigned_employee
  )
  if (selectedEmp) {
    if (selectedEmp.company_id) {
      orgForm.company = selectedEmp.company_id
      const branchRes = await listBranches({ company: orgForm.company, page_size: 200 })
      orgBranches.value = branchRes.data.results || []
    }
    if (selectedEmp.branch_id) {
      orgForm.branch = selectedEmp.branch_id
      const deptRes = await listDepartments({ branch: orgForm.branch, page_size: 200 })
      orgDepartments.value = deptRes.data.results || []
    }
    if (selectedEmp.department) {
      orgForm.department = selectedEmp.department
    }
  }
}

async function onOrgCompanyChange() {
  orgForm.branch = ''
  orgForm.department = ''
  orgBranches.value = []
  orgDepartments.value = []
  if (!orgForm.company) return
  const { data } = await listBranches({ company: orgForm.company, page_size: 200 })
  orgBranches.value = data.results || []
}

async function onOrgBranchChange() {
  orgForm.department = ''
  orgDepartments.value = []
  if (!orgForm.branch) return
  const { data } = await listDepartments({ branch: orgForm.branch, page_size: 200 })
  orgDepartments.value = data.results || []
}

async function onOrgDepartmentChange() {
  if (!orgForm.department) return
  const { data } = await listEmployees({ department: orgForm.department, page_size: 200 })
  orgEmployees.value = data.results || []
}

async function startEditOrg() {
  orgErrorMessage.value = ''
  isEditingOrg.value = true
  orgForm.company = device.value.company_id || ''
  orgForm.branch = device.value.branch_id || ''
  orgForm.department = device.value.department_id || ''
  orgForm.assigned_employee = device.value.assigned_employee_id || ''
  orgBranches.value = []
  orgDepartments.value = []

  // Pre-load all employees so admin can select immediately
  const empAllRes = await listEmployees({ page_size: 500 })
  allOrgEmployees.value = empAllRes.data.results || []

  const { data } = await listCompanies({ page_size: 200 })
  orgCompanies.value = data.results || []

  // If employee is assigned but company/branch/dept were not filled, cascade from employee
  if (orgForm.assigned_employee && (!orgForm.company || !orgForm.branch || !orgForm.department)) {
    const matched = allOrgEmployees.value.find(
      (e) => e.id === Number(orgForm.assigned_employee) || e.id === orgForm.assigned_employee
    )
    if (matched) {
      if (!orgForm.company && matched.company_id) orgForm.company = matched.company_id
      if (!orgForm.branch && matched.branch_id) orgForm.branch = matched.branch_id
      if (!orgForm.department && matched.department) orgForm.department = matched.department
    }
  }

  if (orgForm.company) {
    const branchRes = await listBranches({ company: orgForm.company, page_size: 200 })
    orgBranches.value = branchRes.data.results || []
  }
  if (orgForm.branch) {
    const deptRes = await listDepartments({ branch: orgForm.branch, page_size: 200 })
    orgDepartments.value = deptRes.data.results || []
  }
}

async function saveOrgAssignment() {
  isSavingOrg.value = true
  orgErrorMessage.value = ''
  try {
    await updateDeviceOrgAssignment(device.value.device_id, {
      company: orgForm.company || null,
      branch: orgForm.branch || null,
      department: orgForm.department || null,
      assigned_employee: orgForm.assigned_employee || null,
    })
    await fetchDevice()
    isEditingOrg.value = false
  } catch (error) {
    orgErrorMessage.value = error.response?.data?.detail || 'Gagal menyimpan assignment.'
  } finally {
    isSavingOrg.value = false
  }
}

async function fetchLatestMetric() {
  try {
    const { data } = await getLatestMetric(route.params.deviceId)
    latestMetric.value = data
  } catch {
    latestMetric.value = null
  }
}

const metricHistory = ref([])
const isHistoryLoading = ref(false)
const historyLoaded = ref(false)

async function fetchMetricHistory() {
  isHistoryLoading.value = true
  try {
    const { data } = await getMetricHistory(route.params.deviceId, { page_size: 200 })
    // Backend orders newest-first (for the "latest sample" use case) — the
    // chart needs chronological order left-to-right.
    metricHistory.value = [...data.results].reverse()
    historyLoaded.value = true
  } catch {
    metricHistory.value = []
  } finally {
    isHistoryLoading.value = false
  }
}

const softwareList = ref([])
const isSoftwareLoading = ref(false)
const softwareSearch = ref('')
const softwareLoaded = ref(false)

async function fetchSoftware() {
  isSoftwareLoading.value = true
  try {
    const { data } = await listSoftware({
      device: route.params.deviceId,
      search: softwareSearch.value || undefined,
      ordering: 'name',
      page_size: 500,
    })
    softwareList.value = data.results
    softwareLoaded.value = true
  } catch {
    softwareList.value = []
  } finally {
    isSoftwareLoading.value = false
  }
}

let softwareSearchDebounce = null
watch(softwareSearch, () => {
  clearTimeout(softwareSearchDebounce)
  softwareSearchDebounce = setTimeout(fetchSoftware, 300)
})

function exportSoftwareCsv() {
  downloadCsv(`software-${device.value.device_id}.csv`, softwareList.value, [
    { key: 'name', label: 'Software' },
    { key: 'version', label: 'Versi' },
    { key: 'publisher', label: 'Publisher' },
    { key: 'install_date', label: 'Tanggal Install' },
  ])
}

const deviceAlerts = ref([])
const isAlertsLoading = ref(false)
const alertsLoaded = ref(false)

async function fetchDeviceAlerts() {
  isAlertsLoading.value = true
  try {
    const { data } = await listAlerts({ device: route.params.deviceId, page_size: 100 })
    deviceAlerts.value = data.results
    alertsLoaded.value = true
  } catch {
    deviceAlerts.value = []
  } finally {
    isAlertsLoading.value = false
  }
}

const locationHistory = ref([])
const isLocationLoading = ref(false)
const locationLoaded = ref(false)

async function fetchLocationHistory() {
  isLocationLoading.value = true
  try {
    const { data } = await getDeviceLocationHistory(route.params.deviceId, { page_size: 50 })
    locationHistory.value = data.results
    locationLoaded.value = true
  } catch {
    locationHistory.value = []
  } finally {
    isLocationLoading.value = false
  }
}

const currentLocation = computed(() => locationHistory.value[0] || null)
const locationMarkers = computed(() =>
  currentLocation.value && currentLocation.value.latitude !== null
    ? [
        {
          lat: currentLocation.value.latitude,
          lng: currentLocation.value.longitude,
          accuracy: currentLocation.value.accuracy_meters,
          popupHtml: `<strong>${device.value.asset ? device.value.asset.asset_code : device.value.hostname}</strong><br>${device.value.hostname}`,
        },
      ]
    : [],
)

const auditLogs = ref([])
const isAuditLoading = ref(false)
const auditLoaded = ref(false)

async function fetchAuditLogs() {
  isAuditLoading.value = true
  try {
    const { data } = await listAuditLogs({ device_id: route.params.deviceId, page_size: 50 })
    auditLogs.value = data.results
    auditLoaded.value = true
  } catch {
    auditLogs.value = []
  } finally {
    isAuditLoading.value = false
  }
}

function formatAuditMetadata(metadata) {
  if (!metadata || Object.keys(metadata).length === 0) return '-'
  return Object.entries(metadata)
    .map(([key, value]) => `${key}=${value}`)
    .join(', ')
}

const appUsage = ref([])
const isAppUsageLoading = ref(false)
const appUsageLoaded = ref(false)
const appUsagePage = reactive({ page: 1, count: 0, currentUrl: null, nextUrl: null, previousUrl: null })
const appUsageDateFrom = ref('')
const appUsageDateTo = ref('')

async function fetchAppUsage(url = null) {
  isAppUsageLoading.value = true
  try {
    const { data } = url
      ? await api.get(url, { baseURL: '' })
      : await listAppUsage({
          device__device_id: route.params.deviceId,
          ordering: '-date,-duration_seconds',
          page_size: ACTIVITY_PAGE_SIZE,
          date__gte: appUsageDateFrom.value || undefined,
          date__lte: appUsageDateTo.value || undefined,
        })
    appUsage.value = data.results
    appUsagePage.count = data.count
    appUsagePage.nextUrl = data.next
    appUsagePage.previousUrl = data.previous
    appUsagePage.currentUrl = url
    appUsageLoaded.value = true
  } catch {
    appUsage.value = []
  } finally {
    isAppUsageLoading.value = false
  }
}

function goAppUsageNext() {
  if (!appUsagePage.nextUrl) return
  appUsagePage.page += 1
  fetchAppUsage(appUsagePage.nextUrl)
}

function goAppUsagePrevious() {
  if (!appUsagePage.previousUrl) return
  appUsagePage.page -= 1
  fetchAppUsage(appUsagePage.previousUrl)
}

function formatDuration(seconds) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.round((seconds % 3600) / 60)
  if (hours > 0) return `${hours}j ${minutes}m`
  return `${minutes}m`
}

const browsingHistory = ref([])
const isBrowsingHistoryLoading = ref(false)
const browsingHistoryLoaded = ref(false)
const browsingHistoryPage = reactive({ page: 1, count: 0, currentUrl: null, nextUrl: null, previousUrl: null })
const browsingHistoryDateFrom = ref('')
const browsingHistoryDateTo = ref('')

async function fetchBrowsingHistory(url = null) {
  isBrowsingHistoryLoading.value = true
  try {
    const { data } = url
      ? await api.get(url, { baseURL: '' })
      : await listBrowsingHistory({
          device__device_id: route.params.deviceId,
          page_size: ACTIVITY_PAGE_SIZE,
          visited_at__gte: browsingHistoryDateFrom.value || undefined,
          visited_at__lte: browsingHistoryDateTo.value ? `${browsingHistoryDateTo.value}T23:59:59` : undefined,
        })
    browsingHistory.value = data.results
    browsingHistoryPage.count = data.count
    browsingHistoryPage.nextUrl = data.next
    browsingHistoryPage.previousUrl = data.previous
    browsingHistoryPage.currentUrl = url
    browsingHistoryLoaded.value = true
  } catch {
    browsingHistory.value = []
  } finally {
    isBrowsingHistoryLoading.value = false
  }
}

function goBrowsingHistoryNext() {
  if (!browsingHistoryPage.nextUrl) return
  browsingHistoryPage.page += 1
  fetchBrowsingHistory(browsingHistoryPage.nextUrl)
}

function goBrowsingHistoryPrevious() {
  if (!browsingHistoryPage.previousUrl) return
  browsingHistoryPage.page -= 1
  fetchBrowsingHistory(browsingHistoryPage.previousUrl)
}

const fileActivity = ref([])
const isFileActivityLoading = ref(false)
const fileActivityLoaded = ref(false)
const fileActivityPage = reactive({ page: 1, count: 0, currentUrl: null, nextUrl: null, previousUrl: null })
const fileActivityDateFrom = ref('')
const fileActivityDateTo = ref('')

async function fetchFileActivity(url = null) {
  isFileActivityLoading.value = true
  try {
    const { data } = url
      ? await api.get(url, { baseURL: '' })
      : await listFileActivity({
          device__device_id: route.params.deviceId,
          page_size: ACTIVITY_PAGE_SIZE,
          occurred_at__gte: fileActivityDateFrom.value || undefined,
          occurred_at__lte: fileActivityDateTo.value ? `${fileActivityDateTo.value}T23:59:59` : undefined,
        })
    fileActivity.value = data.results
    fileActivityPage.count = data.count
    fileActivityPage.nextUrl = data.next
    fileActivityPage.previousUrl = data.previous
    fileActivityPage.currentUrl = url
    fileActivityLoaded.value = true
  } catch {
    fileActivity.value = []
  } finally {
    isFileActivityLoading.value = false
  }
}

function goFileActivityNext() {
  if (!fileActivityPage.nextUrl) return
  fileActivityPage.page += 1
  fetchFileActivity(fileActivityPage.nextUrl)
}

function goFileActivityPrevious() {
  if (!fileActivityPage.previousUrl) return
  fileActivityPage.page -= 1
  fetchFileActivity(fileActivityPage.previousUrl)
}

const systemErrors = ref([])
const isSystemErrorsLoading = ref(false)
const systemErrorsLoaded = ref(false)
const systemErrorsPage = reactive({ page: 1, count: 0, currentUrl: null, nextUrl: null, previousUrl: null })
const systemErrorsLevelFilter = ref('')
const systemErrorsDateFrom = ref('')
const systemErrorsDateTo = ref('')
const systemErrorDetail = ref(null)

function systemErrorSearchUrl(row) {
  const query = `"${row.provider}" event ${row.event_id} error windows`
  return `https://www.google.com/search?q=${encodeURIComponent(query)}`
}

async function fetchSystemErrors(url = null) {
  isSystemErrorsLoading.value = true
  try {
    const { data } = url
      ? await api.get(url, { baseURL: '' })
      : await listSystemErrors({
          device__device_id: route.params.deviceId,
          page_size: ACTIVITY_PAGE_SIZE,
          level: systemErrorsLevelFilter.value || undefined,
          occurred_at__gte: systemErrorsDateFrom.value || undefined,
          occurred_at__lte: systemErrorsDateTo.value ? `${systemErrorsDateTo.value}T23:59:59` : undefined,
        })
    systemErrors.value = data.results
    systemErrorsPage.count = data.count
    systemErrorsPage.nextUrl = data.next
    systemErrorsPage.previousUrl = data.previous
    systemErrorsPage.currentUrl = url
    systemErrorsLoaded.value = true
  } catch {
    systemErrors.value = []
  } finally {
    isSystemErrorsLoading.value = false
  }
}

function goSystemErrorsNext() {
  if (!systemErrorsPage.nextUrl) return
  systemErrorsPage.page += 1
  fetchSystemErrors(systemErrorsPage.nextUrl)
}

function goSystemErrorsPrevious() {
  if (!systemErrorsPage.previousUrl) return
  systemErrorsPage.page -= 1
  fetchSystemErrors(systemErrorsPage.previousUrl)
}

// These three sync from the agent every 2-10 minutes, not live — auto-polling
// the list every 20s while the tab is open means new data shows up on its own
// instead of looking "stuck" until the admin clicks away and back.
const ACTIVITY_AUTO_REFRESH_INTERVAL_MS = 20000
let activityAutoRefreshTimer = null

function stopActivityAutoRefresh() {
  clearInterval(activityAutoRefreshTimer)
  activityAutoRefreshTimer = null
}

function startActivityAutoRefresh(fetchFn) {
  stopActivityAutoRefresh()
  activityAutoRefreshTimer = setInterval(fetchFn, ACTIVITY_AUTO_REFRESH_INTERVAL_MS)
}

watch([appUsageDateFrom, appUsageDateTo], () => {
  if (!appUsageLoaded.value) return
  appUsagePage.page = 1
  fetchAppUsage()
})

watch([browsingHistoryDateFrom, browsingHistoryDateTo], () => {
  if (!browsingHistoryLoaded.value) return
  browsingHistoryPage.page = 1
  fetchBrowsingHistory()
})

watch([fileActivityDateFrom, fileActivityDateTo], () => {
  if (!fileActivityLoaded.value) return
  fileActivityPage.page = 1
  fetchFileActivity()
})

watch([systemErrorsLevelFilter, systemErrorsDateFrom, systemErrorsDateTo], () => {
  if (!systemErrorsLoaded.value) return
  systemErrorsPage.page = 1
  fetchSystemErrors()
})

watch(activeTab, (tab) => {
  if (tab === 'software' && !softwareLoaded.value) fetchSoftware()
  if (tab === 'alerts' && !alertsLoaded.value) fetchDeviceAlerts()
  if (tab === 'location' && !locationLoaded.value) fetchLocationHistory()
  if (tab === 'metrics' && !historyLoaded.value) fetchMetricHistory()
  if (tab === 'audit' && !auditLoaded.value) fetchAuditLogs()

  if (tab === 'app-usage') {
    if (!appUsageLoaded.value) fetchAppUsage()
    startActivityAutoRefresh(() => fetchAppUsage(appUsagePage.currentUrl))
  } else if (tab === 'browsing-history') {
    if (!browsingHistoryLoaded.value) fetchBrowsingHistory()
    startActivityAutoRefresh(() => fetchBrowsingHistory(browsingHistoryPage.currentUrl))
  } else if (tab === 'file-activity') {
    if (!fileActivityLoaded.value) fetchFileActivity()
    startActivityAutoRefresh(() => fetchFileActivity(fileActivityPage.currentUrl))
  } else if (tab === 'system-errors') {
    if (!systemErrorsLoaded.value) fetchSystemErrors()
    startActivityAutoRefresh(() => fetchSystemErrors(systemErrorsPage.currentUrl))
  } else {
    stopActivityAutoRefresh()
  }
})

onBeforeUnmount(stopActivityAutoRefresh)

onMounted(() => {
  fetchDevice()
  fetchLatestMetric()
  fetchRiskScore()
  fetchTodayIdleStat()
})

async function confirmToggle() {
  confirmOpen.value = false
  try {
    if (toggleAction.value === 'disable') {
      await disableDevice(device.value.device_id)
    } else {
      await enableDevice(device.value.device_id)
    }
    await fetchDevice()
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || 'Aksi gagal dilakukan.'
  }
}

// Non-destructive, so it skips the confirm dialog (same as DeviceListView).
async function handleApprove() {
  try {
    await approveDevice(device.value.device_id)
    await fetchDevice()
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || 'Gagal approve device.'
  }
}

const isRotatingToken = ref(false)
const rotatedTokenInfo = reactive({ open: false, token: '', deviceId: '' })

async function handleRotateToken() {
  if (!confirm(`Yakin ingin merotasi token untuk device ${device.value.device_id}? Token lama akan dinonaktifkan dan diganti dengan token baru.`)) {
    return
  }
  isRotatingToken.value = true
  try {
    const { data } = await rotateDeviceToken(device.value.device_id)
    rotatedTokenInfo.token = data.device_token
    rotatedTokenInfo.deviceId = data.device_id
    rotatedTokenInfo.open = true
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || 'Gagal merotasi token perangkat.'
  } finally {
    isRotatingToken.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <button class="text-sm text-brand-600 hover:underline" @click="router.push({ name: 'devices' })">
      &larr; Kembali ke daftar Devices
    </button>

    <div v-if="isLoading" class="rounded-xl bg-white p-6 text-center text-slate-400 shadow-sm ring-1 ring-slate-900/5">
      Memuat data...
    </div>

    <div v-else-if="errorMessage" class="rounded-xl bg-white p-6 text-center text-red-500 shadow-sm ring-1 ring-slate-900/5">
      {{ errorMessage }}
    </div>

    <template v-else-if="device">
      <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
        <div>
          <div class="flex items-center gap-3">
            <h1 class="text-lg font-semibold text-slate-800">{{ device.asset ? device.asset.asset_code : device.hostname }}</h1>
            <StatusBadge :status="displayStatus" />
            <span
              v-if="!device.is_approved"
              class="inline-block rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-700"
              title="Device ini terdaftar otomatis — menunggu persetujuan (approval) admin"
            >
              Pending Approval
            </span>
          </div>
          <p class="mt-1 text-sm text-slate-500">
            {{ device.hostname }} &middot; {{ device.username || 'Tidak ada user login' }}
          </p>
        </div>
        <div class="flex gap-2">
          <button
            v-if="auth.hasPermission('agent.manage')"
            :disabled="isRotatingToken"
            class="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            @click="handleRotateToken"
          >
            {{ isRotatingToken ? 'Merotasi...' : 'Rotasi Token' }}
          </button>
          <button
            v-if="!device.is_approved && auth.hasPermission('device.disable')"
            class="rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-700"
            @click="handleApprove"
          >
            Approve Device
          </button>
          <button
            v-if="auth.hasPermission('device.disable')"
            class="rounded-md px-3 py-1.5 text-sm font-medium text-white"
            :class="toggleAction === 'disable' ? 'bg-red-600 hover:bg-red-700' : 'bg-emerald-600 hover:bg-emerald-700'"
            @click="confirmOpen = true"
          >
            {{ toggleAction === 'disable' ? 'Disable Device' : 'Enable Device' }}
          </button>
        </div>
      </div>

      <div class="rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
        <div class="flex flex-wrap border-b border-slate-200 px-2">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="border-b-2 px-4 py-3 text-sm font-medium"
            :class="
              activeTab === tab.key ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500 hover:text-slate-700'
            "
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>

        <div class="p-6">
          <div v-if="activeTab === 'overview'" class="space-y-6">
            <div class="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
              <div><dt class="text-xs uppercase text-slate-400">Hostname</dt><dd>{{ device.hostname }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">Computer Name</dt><dd>{{ device.computer_name || '-' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">Logged-in User</dt><dd>{{ device.username || '-' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">IP Address</dt><dd>{{ device.ip_address || '-' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">MAC Address</dt><dd>{{ device.mac_address || '-' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">Agent Version</dt><dd>{{ device.agent_version || '-' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">First Registered</dt><dd>{{ new Date(device.first_registered).toLocaleString() }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">Last Seen</dt><dd>{{ timeAgo(displayLastSeen) }}</dd></div>
            </div>

            <div v-if="auth.hasPermission('alert.view')" class="border-t border-slate-100 pt-5">
              <h3 class="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Behavioral Risk Score
                <span class="normal-case text-slate-400">(30 hari terakhir)</span>
              </h3>
              <div v-if="isRiskScoreLoading" class="text-sm text-slate-400">Memuat...</div>
              <div v-else-if="!riskScore" class="text-sm text-slate-400">Gagal memuat risk score.</div>
              <template v-else>
                <div class="flex items-center gap-4">
                  <div class="rounded-lg border px-4 py-3 text-center" :class="RISK_LEVEL_STYLE[riskScore.level]">
                    <div class="text-2xl font-bold">{{ riskScore.score }}</div>
                    <div class="text-xs font-semibold uppercase tracking-wide">{{ riskScore.level }}</div>
                  </div>
                  <p class="max-w-md text-xs text-slate-400">
                    Skor diolah otomatis dari riwayat alert device ini (USB, kebocoran data, aktivitas luar jam
                    kerja, software baru, dll) — sinyal untuk triase, bukan vonis.
                  </p>
                </div>
                <div v-if="riskScore.breakdown.length > 0" class="mt-3 space-y-1.5">
                  <div
                    v-for="row in riskScore.breakdown"
                    :key="row.category"
                    class="flex items-center justify-between text-sm"
                  >
                    <span class="text-slate-600">{{ RISK_CATEGORY_LABELS[row.category] || row.category }}</span>
                    <span class="text-slate-400">
                      {{ row.count }}x ({{ row.unresolved_count }} belum selesai) · {{ row.points }} poin
                    </span>
                  </div>
                </div>
              </template>
            </div>

            <div v-if="auth.hasPermission('activity.view')" class="border-t border-slate-100 pt-5">
              <h3 class="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Aktivitas Hari Ini</h3>
              <div v-if="isIdleStatLoading" class="text-sm text-slate-400">Memuat...</div>
              <div v-else-if="!todayIdleStat" class="text-sm text-slate-400">
                Belum ada data idle activity untuk device ini. Muncul otomatis setelah agent sync (maks. 5 menit sekali) — kalau tetap kosong lama, cek apakah IDLE_ACTIVITY_MONITOR_ENABLED aktif di .env agent.
              </div>
              <div v-else class="flex items-center gap-4">
                <div
                  class="rounded-lg border px-4 py-3 text-center"
                  :class="
                    todayIdleStat.active_percent >= 60
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : todayIdleStat.active_percent >= 30
                      ? 'bg-amber-50 text-amber-700 border-amber-200'
                      : 'bg-slate-50 text-slate-500 border-slate-200'
                  "
                >
                  <div class="text-2xl font-bold">{{ todayIdleStat.active_percent }}%</div>
                  <div class="text-xs font-semibold uppercase tracking-wide">Aktif</div>
                </div>
                <p class="max-w-md text-xs text-slate-400">
                  Berdasarkan aktivitas mouse/keyboard sistem (kapan, bukan apa yang diketik) —
                  {{ Math.round(todayIdleStat.active_seconds / 60) }} menit aktif,
                  {{ Math.round(todayIdleStat.idle_seconds / 60) }} menit idle hari ini.
                </p>
              </div>
            </div>

            <div class="border-t border-slate-100 pt-5">
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-400">Biodata Pengguna</h3>
                <button
                  v-if="auth.hasPermission('device.manage') && !isEditingOrg"
                  class="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
                  @click="startEditOrg"
                >
                  Edit
                </button>
              </div>

              <div v-if="!isEditingOrg" class="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
                <div><dt class="text-xs uppercase text-slate-400">Company</dt><dd>{{ device.company || 'Belum diatur' }}</dd></div>
                <div><dt class="text-xs uppercase text-slate-400">Branch</dt><dd>{{ device.branch_name || 'Belum diatur' }}</dd></div>
                <div><dt class="text-xs uppercase text-slate-400">Department</dt><dd>{{ device.department_name || 'Belum diatur' }}</dd></div>
                <div><dt class="text-xs uppercase text-slate-400">Assigned Employee</dt><dd>{{ device.assigned_employee || 'Belum diatur' }}</dd></div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Asset Code</dt>
                  <dd v-if="device.asset" class="font-mono">
                    {{ device.asset.asset_code }}
                    <span class="ml-1 text-xs text-slate-400">({{ device.asset.kondisi }}, {{ device.asset.status_barang }})</span>
                  </dd>
                  <dd v-else class="text-slate-400">
                    Belum ter-sync dari asset_dfm —
                    <router-link to="/assets" class="text-brand-600 hover:underline">lihat halaman Assets</router-link>
                  </dd>
                </div>
              </div>

              <div v-else class="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div class="grid grid-cols-1 gap-3 sm:grid-cols-4">
                  <div>
                    <label class="mb-1 block text-xs font-semibold text-brand-700">Pilih Karyawan</label>
                    <select
                      v-model="orgForm.assigned_employee"
                      class="w-full rounded-md border border-brand-300 bg-white px-2 py-1.5 text-sm font-medium focus:border-brand-500 focus:outline-none"
                      @change="onOrgEmployeeChange"
                    >
                      <option value="">-- Pilih Karyawan --</option>
                      <option v-for="e in allOrgEmployees" :key="e.id" :value="e.id">
                        {{ e.full_name }} — {{ e.branch_name || 'Kantor' }} ({{ e.department_name || e.position || 'Staff' }})
                      </option>
                    </select>
                  </div>
                  <div>
                    <label class="mb-1 block text-xs font-medium text-slate-600">Cabang (Branch)</label>
                    <select
                      v-model="orgForm.branch"
                      class="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400"
                      @change="onOrgBranchChange"
                    >
                      <option value="">Tidak diisi</option>
                      <option v-for="b in orgBranches" :key="b.id" :value="b.id">{{ b.name }}</option>
                    </select>
                  </div>
                  <div>
                    <label class="mb-1 block text-xs font-medium text-slate-600">Departemen (Unit Kerja)</label>
                    <select
                      v-model="orgForm.department"
                      class="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400"
                      @change="onOrgDepartmentChange"
                    >
                      <option value="">Tidak diisi</option>
                      <option v-for="d in orgDepartments" :key="d.id" :value="d.id">{{ d.name }}</option>
                    </select>
                  </div>
                  <div>
                    <label class="mb-1 block text-xs font-medium text-slate-600">Perusahaan (PT)</label>
                    <select
                      v-model="orgForm.company"
                      class="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                      @change="onOrgCompanyChange"
                    >
                      <option value="">Tidak diisi</option>
                      <option v-for="c in orgCompanies" :key="c.id" :value="c.id">{{ c.name }}</option>
                    </select>
                  </div>
                </div>
                <p v-if="orgErrorMessage" class="text-sm text-red-600">{{ orgErrorMessage }}</p>
                <div class="flex justify-end gap-2">
                  <button
                    class="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-white"
                    @click="isEditingOrg = false"
                  >
                    Batal
                  </button>
                  <button
                    :disabled="isSavingOrg"
                    class="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
                    @click="saveOrgAssignment"
                  >
                    {{ isSavingOrg ? 'Menyimpan...' : 'Simpan' }}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div v-else-if="activeTab === 'hardware'" class="space-y-6">
            <div class="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
              <div><dt class="text-xs uppercase text-slate-400">OS</dt><dd>{{ device.os_name || '-' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">OS Version</dt><dd>{{ device.os_version || '-' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">Architecture</dt><dd>{{ device.architecture || '-' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">Manufacturer</dt><dd>{{ device.manufacturer || 'Not Available' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">Model</dt><dd>{{ device.model || 'Not Available' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">Nama Model</dt><dd>{{ device.system_family || 'Not Available' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">Serial Number</dt><dd>{{ device.serial_number || 'Not Available' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">Motherboard</dt><dd>{{ device.motherboard || 'Not Available' }}</dd></div>
              <div><dt class="text-xs uppercase text-slate-400">BIOS Version</dt><dd>{{ device.bios_version || 'Not Available' }}</dd></div>
            </div>

            <div class="border-t border-slate-100 pt-5">
              <h3 class="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">CPU</h3>
              <div class="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
                <div><dt class="text-xs uppercase text-slate-400">Model</dt><dd>{{ device.cpu || '-' }}</dd></div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Cores / Threads / Speed</dt>
                  <dd>
                    <template v-if="device.cpu_cores">
                      {{ device.cpu_cores }} cores / {{ device.cpu_threads || '-' }} threads / {{ device.cpu_speed_mhz || '-' }} MHz
                    </template>
                    <template v-else>Not Available</template>
                  </dd>
                </div>
              </div>
            </div>

            <div class="border-t border-slate-100 pt-5">
              <h3 class="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">GPU</h3>
              <div v-if="device.gpu_details?.length" class="space-y-2">
                <div v-for="(gpu, idx) in device.gpu_details" :key="idx" class="text-sm">
                  <span class="font-medium text-slate-700">{{ gpu.name }}</span>
                  <span class="text-slate-500">
                    — {{ gpu.vram_mb ? `${(gpu.vram_mb / 1024).toFixed(1)} GB VRAM` : 'VRAM tidak diketahui' }},
                    driver {{ gpu.driver_version || '-' }}
                  </span>
                </div>
              </div>
              <p v-else class="text-sm text-slate-400">Not Available</p>
            </div>

            <div class="border-t border-slate-100 pt-5">
              <h3 class="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">RAM ({{ device.ram || '-' }} total)</h3>
              <div v-if="device.ram_details?.length" class="overflow-x-auto rounded-lg border border-slate-100">
                <table class="min-w-full divide-y divide-slate-100 text-sm">
                  <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                    <tr>
                      <th class="px-4 py-2">Slot</th>
                      <th class="px-4 py-2">Kapasitas</th>
                      <th class="px-4 py-2">Kecepatan</th>
                      <th class="px-4 py-2">Manufacturer</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100">
                    <tr v-for="(stick, idx) in device.ram_details" :key="idx">
                      <td class="px-4 py-2 text-slate-600">{{ stick.slot || '-' }}</td>
                      <td class="px-4 py-2 text-slate-600">{{ stick.capacity_gb ? `${stick.capacity_gb} GB` : '-' }}</td>
                      <td class="px-4 py-2 text-slate-600">{{ stick.speed_mhz ? `${stick.speed_mhz} MHz` : '-' }}</td>
                      <td class="px-4 py-2 text-slate-600">{{ stick.manufacturer || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-else class="text-sm text-slate-400">Detail per-slot Not Available</p>
            </div>

            <div class="border-t border-slate-100 pt-5">
              <h3 class="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Disk ({{ device.disk || '-' }} total)</h3>
              <div v-if="device.disk_details?.length" class="overflow-x-auto rounded-lg border border-slate-100">
                <table class="min-w-full divide-y divide-slate-100 text-sm">
                  <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                    <tr>
                      <th class="px-4 py-2">Model</th>
                      <th class="px-4 py-2">Ukuran</th>
                      <th class="px-4 py-2">Tipe</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100">
                    <tr v-for="(disk, idx) in device.disk_details" :key="idx">
                      <td class="px-4 py-2 text-slate-600">{{ disk.model || '-' }}</td>
                      <td class="px-4 py-2 text-slate-600">{{ disk.size_gb ? `${disk.size_gb} GB` : '-' }}</td>
                      <td class="px-4 py-2">
                        <span
                          class="rounded-full px-2 py-0.5 text-xs font-medium"
                          :class="disk.media_type === 'SSD' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'"
                        >
                          {{ disk.media_type || 'Unknown' }}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-else class="text-sm text-slate-400">Detail per-disk Not Available</p>
            </div>

            <div class="border-t border-slate-100 pt-5">
              <h3 class="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Kesehatan Baterai</h3>
              <div v-if="device.battery_health_percent !== null" class="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-3">
                <div>
                  <dt class="text-xs uppercase text-slate-400">Kesehatan</dt>
                  <dd
                    class="font-medium"
                    :class="device.battery_health_percent < 60 ? 'text-red-600' : device.battery_health_percent < 80 ? 'text-amber-600' : 'text-emerald-600'"
                  >
                    {{ device.battery_health_percent }}%
                  </dd>
                </div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Kapasitas Desain</dt>
                  <dd>{{ (device.battery_design_capacity_mwh / 1000).toFixed(1) }} Wh</dd>
                </div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Kapasitas Sekarang (Full Charge)</dt>
                  <dd>{{ (device.battery_full_charge_capacity_mwh / 1000).toFixed(1) }} Wh</dd>
                </div>
              </div>
              <p v-else class="text-sm text-slate-400">
                Not Available (desktop tanpa baterai, atau data belum tersinkron)
              </p>
            </div>

            <div class="border-t border-slate-100 pt-5">
              <h3 class="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Compliance <span class="normal-case text-slate-400">(dicek ulang tiap 1 jam oleh agent)</span>
              </h3>
              <div class="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-3">
                <div>
                  <dt class="text-xs uppercase text-slate-400">BitLocker</dt>
                  <dd>
                    <span
                      class="rounded-full px-2 py-0.5 text-xs font-semibold"
                      :class="
                        device.bitlocker_enabled === true
                          ? 'bg-emerald-100 text-emerald-700'
                          : device.bitlocker_enabled === false
                          ? 'bg-red-100 text-red-700'
                          : 'bg-slate-100 text-slate-500'
                      "
                    >
                      {{ device.bitlocker_enabled === true ? 'Aktif' : device.bitlocker_enabled === false ? 'Nonaktif' : 'Tidak diketahui' }}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Firewall</dt>
                  <dd>
                    <span
                      class="rounded-full px-2 py-0.5 text-xs font-semibold"
                      :class="
                        device.firewall_enabled === true
                          ? 'bg-emerald-100 text-emerald-700'
                          : device.firewall_enabled === false
                          ? 'bg-red-100 text-red-700'
                          : 'bg-slate-100 text-slate-500'
                      "
                    >
                      {{ device.firewall_enabled === true ? 'Aktif' : device.firewall_enabled === false ? 'Nonaktif' : 'Tidak diketahui' }}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Antivirus</dt>
                  <dd>
                    <span
                      class="rounded-full px-2 py-0.5 text-xs font-semibold"
                      :class="
                        device.antivirus_enabled === true
                          ? 'bg-emerald-100 text-emerald-700'
                          : device.antivirus_enabled === false
                          ? 'bg-red-100 text-red-700'
                          : 'bg-slate-100 text-slate-500'
                      "
                    >
                      {{ device.antivirus_name || (device.antivirus_enabled === null ? 'Tidak diketahui' : 'Tidak terdeteksi') }}
                    </span>
                  </dd>
                </div>
              </div>
            </div>

            <p class="text-xs text-slate-400">
              Pemakaian CPU/RAM/Disk secara realtime ada di tab Metrics.
            </p>
          </div>

          <div v-else-if="activeTab === 'metrics'" class="space-y-6">
            <div v-if="!metric.recorded_at && !liveMetric" class="py-10 text-center text-sm text-slate-400">
              Belum ada data metrics dari device ini. Pastikan agent sudah berjalan.
            </div>
            <template v-else>
              <div class="grid grid-cols-1 gap-6 sm:grid-cols-3">
                <UsageBar label="CPU" :percent="metric.cpu_percent" />
                <UsageBar label="RAM" :percent="metric.ram_percent" />
                <UsageBar label="Disk" :percent="metric.disk_percent" />
              </div>

              <div class="grid grid-cols-1 gap-x-8 gap-y-4 border-t border-slate-100 pt-5 sm:grid-cols-3">
                <div>
                  <dt class="text-xs uppercase text-slate-400">Battery</dt>
                  <dd>
                    {{ metric.battery_percent === null ? 'Not Available' : `${Math.round(metric.battery_percent)}%` }}
                    <span v-if="metric.battery_charging" class="text-xs text-emerald-600">(Charging)</span>
                  </dd>
                </div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Network Upload</dt>
                  <dd>{{ metric.net_upload_kbps === null ? 'Not Available' : `${Math.round(metric.net_upload_kbps)} kbps` }}</dd>
                </div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Network Download</dt>
                  <dd>{{ metric.net_download_kbps === null ? 'Not Available' : `${Math.round(metric.net_download_kbps)} kbps` }}</dd>
                </div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Uptime</dt>
                  <dd>{{ formatUptime(metric.uptime_seconds) }}</dd>
                </div>
                <div>
                  <dt class="text-xs uppercase text-slate-400">Sampel Terakhir</dt>
                  <dd>{{ metric.recorded_at ? timeAgo(metric.recorded_at) : 'Live' }}</dd>
                </div>
              </div>

              <div class="border-t border-slate-100 pt-5">
                <h3 class="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Tren CPU/RAM/Disk</h3>
                <div v-if="isHistoryLoading" class="py-10 text-center text-sm text-slate-400">Memuat grafik...</div>
                <MetricTrendChart v-else :samples="metricHistory" />
              </div>
            </template>
          </div>

          <div v-else-if="activeTab === 'software'" class="space-y-3">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <input
                v-model="softwareSearch"
                type="text"
                placeholder="Cari nama atau publisher..."
                class="w-64 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <button
                class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                :disabled="softwareList.length === 0"
                @click="exportSoftwareCsv"
              >
                Export CSV
              </button>
            </div>
            <div class="overflow-x-auto rounded-lg border border-slate-100">
              <table class="min-w-full divide-y divide-slate-100 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  <tr>
                    <th class="px-4 py-2">Software</th>
                    <th class="px-4 py-2">Versi</th>
                    <th class="px-4 py-2">Publisher</th>
                    <th class="px-4 py-2">Tanggal Install</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-if="isSoftwareLoading">
                    <td colspan="4" class="px-4 py-6 text-center text-slate-400">Memuat data...</td>
                  </tr>
                  <tr v-else-if="softwareList.length === 0">
                    <td colspan="4" class="px-4 py-6 text-center text-slate-400">
                      Belum ada data software. Muncul otomatis setelah agent sync (maks. 1 jam sekali).
                    </td>
                  </tr>
                  <tr v-for="item in softwareList" v-else :key="item.id" class="hover:bg-slate-50">
                    <td class="px-4 py-2 font-medium text-slate-700">{{ item.name }}</td>
                    <td class="px-4 py-2 text-slate-500">{{ item.version || '-' }}</td>
                    <td class="px-4 py-2 text-slate-500">{{ item.publisher || '-' }}</td>
                    <td class="px-4 py-2 text-slate-500">{{ item.install_date || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-else-if="activeTab === 'alerts'" class="space-y-3">
            <div class="overflow-x-auto rounded-lg border border-slate-100">
              <table class="min-w-full divide-y divide-slate-100 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  <tr>
                    <th class="px-4 py-2">Alert</th>
                    <th class="px-4 py-2">Status</th>
                    <th class="px-4 py-2">Terjadi</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-if="isAlertsLoading">
                    <td colspan="3" class="px-4 py-6 text-center text-slate-400">Memuat data...</td>
                  </tr>
                  <tr v-else-if="deviceAlerts.length === 0">
                    <td colspan="3" class="px-4 py-6 text-center text-slate-400">
                      Belum ada alert untuk device ini.
                    </td>
                  </tr>
                  <tr v-for="alert in deviceAlerts" v-else :key="alert.id" class="hover:bg-slate-50">
                    <td class="px-4 py-2 align-top">
                      <span
                        class="mb-1 inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold"
                        :class="ALERT_SEVERITY_STYLE[alert.severity]"
                      >
                        {{ alert.severity }}
                      </span>
                      <div class="break-words text-slate-600">{{ alert.message }}</div>
                    </td>
                    <td class="px-4 py-2 align-top">
                      <span class="rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="ALERT_STATUS_STYLE[alert.status]">
                        {{ alert.status }}
                      </span>
                    </td>
                    <td class="px-4 py-2 align-top text-slate-500">{{ timeAgo(alert.triggered_at) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-else-if="activeTab === 'location'" class="space-y-4">
            <div v-if="isLocationLoading" class="py-10 text-center text-sm text-slate-400">Memuat data...</div>
            <template v-else-if="locationHistory.length === 0">
              <div class="py-10 text-center text-sm text-slate-400">
                Belum ada data lokasi. Muncul otomatis setelah agent sync (maks. 15 menit sekali).
              </div>
            </template>
            <template v-else>
              <div v-if="currentLocation.latitude !== null" class="space-y-3">
                <div class="rounded-lg border border-slate-100 p-2">
                  <LeafletMap :markers="locationMarkers" height="280px" />
                </div>
                <p class="text-xs text-slate-400">
                  Sumber: <strong>{{ currentLocation.source === 'OS' ? 'Windows Location Service' : 'Estimasi IP geolocation (perkiraan, bukan koordinat presisi)' }}</strong>
                  &middot; akurasi ±{{ Math.round(currentLocation.accuracy_meters || 0) }} m
                  &middot; {{ timeAgo(currentLocation.recorded_at) }}
                </p>
              </div>
              <div v-else class="rounded-lg bg-slate-50 p-4 text-sm text-slate-500">
                Lokasi terkini tidak diketahui — Windows Location Service tidak tersedia dan alamat IP
                device tidak bisa diestimasi (kemungkinan jaringan lokal/privat).
              </div>

              <div>
                <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Riwayat Lokasi</h3>
                <div class="overflow-x-auto rounded-lg border border-slate-100">
                  <table class="min-w-full divide-y divide-slate-100 text-sm">
                    <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                      <tr>
                        <th class="px-4 py-2">Waktu</th>
                        <th class="px-4 py-2">Sumber</th>
                        <th class="px-4 py-2">Koordinat</th>
                        <th class="px-4 py-2">Akurasi</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                      <tr v-for="loc in locationHistory" :key="loc.id" class="hover:bg-slate-50">
                        <td class="px-4 py-2 text-slate-500">{{ timeAgo(loc.recorded_at) }}</td>
                        <td class="px-4 py-2">
                          <span
                            class="rounded-full px-2 py-0.5 text-xs font-medium"
                            :class="loc.source === 'OS' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'"
                          >
                            {{ loc.source === 'OS' ? 'OS Location' : 'Estimasi IP' }}
                          </span>
                        </td>
                        <td class="px-4 py-2 font-mono text-xs text-slate-600">
                          {{ loc.latitude !== null ? `${loc.latitude.toFixed(5)}, ${loc.longitude.toFixed(5)}` : 'Tidak diketahui' }}
                        </td>
                        <td class="px-4 py-2 text-slate-500">
                          {{ loc.accuracy_meters ? `±${Math.round(loc.accuracy_meters)} m` : '-' }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </template>
          </div>

          <div v-else-if="activeTab === 'live-screen'">
            <LiveScreenPanel :key="device.device_id" :device-id="device.device_id" />
          </div>

          <div v-else-if="activeTab === 'app-usage'" class="space-y-3">
            <div class="flex items-center justify-between">
              <p class="text-xs text-slate-400">
                Total waktu tiap aplikasi digunakan di foreground, per hari. Agent sync tiap 5 menit — halaman ini
                otomatis refresh tiap 20 detik.
              </p>
              <button
                class="shrink-0 rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
                @click="fetchAppUsage"
              >
                Refresh
              </button>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <label class="text-xs text-slate-500">Dari</label>
              <input
                v-model="appUsageDateFrom"
                type="date"
                :max="appUsageDateTo || undefined"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <label class="text-xs text-slate-500">Sampai</label>
              <input
                v-model="appUsageDateTo"
                type="date"
                :min="appUsageDateFrom || undefined"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <button
                v-if="appUsageDateFrom || appUsageDateTo"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-500 hover:bg-slate-50"
                @click="appUsageDateFrom = ''; appUsageDateTo = ''"
              >
                Reset
              </button>
            </div>
            <div class="overflow-x-auto rounded-lg border border-slate-100">
              <table class="min-w-full divide-y divide-slate-100 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  <tr>
                    <th class="px-4 py-2">Tanggal</th>
                    <th class="px-4 py-2">Aplikasi</th>
                    <th class="px-4 py-2">Judul Terakhir</th>
                    <th class="px-4 py-2">Durasi</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-if="isAppUsageLoading">
                    <td colspan="4" class="px-4 py-6 text-center text-slate-400">Memuat data...</td>
                  </tr>
                  <tr v-else-if="appUsage.length === 0">
                    <td colspan="4" class="px-4 py-6 text-center text-slate-400">
                      Belum ada data app usage untuk device ini. Muncul otomatis setelah agent sync — kalau tetap kosong lama, cek apakah APP_USAGE_MONITOR_ENABLED aktif di .env agent.
                    </td>
                  </tr>
                  <tr v-for="row in appUsage" v-else :key="row.id" class="hover:bg-slate-50">
                    <td class="px-4 py-2 whitespace-nowrap text-slate-500">{{ row.date }}</td>
                    <td class="px-4 py-2 font-medium text-slate-700">{{ row.app_name }}</td>
                    <td class="px-4 py-2 text-xs text-slate-500">{{ row.window_title || '-' }}</td>
                    <td class="px-4 py-2 text-slate-600">{{ formatDuration(row.duration_seconds) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <Pagination
              v-if="!isAppUsageLoading && appUsage.length > 0"
              :page="appUsagePage.page"
              :page-size="ACTIVITY_PAGE_SIZE"
              :count="appUsagePage.count"
              :has-previous="Boolean(appUsagePage.previousUrl)"
              :has-next="Boolean(appUsagePage.nextUrl)"
              @previous="goAppUsagePrevious"
              @next="goAppUsageNext"
            />
          </div>

          <div v-else-if="activeTab === 'browsing-history'" class="space-y-3">
            <div class="flex items-center justify-between">
              <p class="text-xs text-slate-400">
                Riwayat situs yang dikunjungi, disinkron dari Chrome/Edge. Agent sync tiap 1 menit — halaman ini
                otomatis refresh tiap 20 detik.
              </p>
              <button
                class="shrink-0 rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
                @click="fetchBrowsingHistory"
              >
                Refresh
              </button>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <label class="text-xs text-slate-500">Dari</label>
              <input
                v-model="browsingHistoryDateFrom"
                type="date"
                :max="browsingHistoryDateTo || undefined"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <label class="text-xs text-slate-500">Sampai</label>
              <input
                v-model="browsingHistoryDateTo"
                type="date"
                :min="browsingHistoryDateFrom || undefined"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <button
                v-if="browsingHistoryDateFrom || browsingHistoryDateTo"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-500 hover:bg-slate-50"
                @click="browsingHistoryDateFrom = ''; browsingHistoryDateTo = ''"
              >
                Reset
              </button>
            </div>
            <div class="overflow-x-auto rounded-lg border border-slate-100">
              <table class="min-w-full divide-y divide-slate-100 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  <tr>
                    <th class="px-4 py-2">Waktu</th>
                    <th class="px-4 py-2">Browser</th>
                    <th class="px-4 py-2">Judul</th>
                    <th class="px-4 py-2">URL</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-if="isBrowsingHistoryLoading">
                    <td colspan="4" class="px-4 py-6 text-center text-slate-400">Memuat data...</td>
                  </tr>
                  <tr v-else-if="browsingHistory.length === 0">
                    <td colspan="4" class="px-4 py-6 text-center text-slate-400">
                      Belum ada data browsing history untuk device ini. Muncul otomatis setelah user browsing & agent sync — kalau tetap kosong lama, cek apakah BROWSER_HISTORY_MONITOR_ENABLED aktif di .env agent.
                    </td>
                  </tr>
                  <tr v-for="row in browsingHistory" v-else :key="row.id" class="hover:bg-slate-50">
                    <td class="px-4 py-2 whitespace-nowrap text-slate-500">{{ new Date(row.visited_at).toLocaleString() }}</td>
                    <td class="px-4 py-2 text-slate-600">{{ row.browser }}</td>
                    <td class="px-4 py-2 max-w-xs truncate" :title="row.title">{{ row.title || '-' }}</td>
                    <td class="px-4 py-2 max-w-xs truncate font-mono text-xs text-brand-700" :title="row.url">
                      <a :href="row.url" target="_blank" rel="noopener noreferrer" class="hover:underline">{{ row.url }}</a>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <Pagination
              v-if="!isBrowsingHistoryLoading && browsingHistory.length > 0"
              :page="browsingHistoryPage.page"
              :page-size="ACTIVITY_PAGE_SIZE"
              :count="browsingHistoryPage.count"
              :has-previous="Boolean(browsingHistoryPage.previousUrl)"
              :has-next="Boolean(browsingHistoryPage.nextUrl)"
              @previous="goBrowsingHistoryPrevious"
              @next="goBrowsingHistoryNext"
            />
          </div>

          <div v-else-if="activeTab === 'file-activity'" class="space-y-3">
            <div class="flex items-center justify-between">
              <p class="text-xs text-slate-400">
                Aktivitas file di folder Desktop/Documents/Downloads (dibuat, diubah, dihapus). Agent sync tiap 2
                menit — halaman ini otomatis refresh tiap 20 detik.
              </p>
              <button
                class="shrink-0 rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
                @click="fetchFileActivity"
              >
                Refresh
              </button>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <label class="text-xs text-slate-500">Dari</label>
              <input
                v-model="fileActivityDateFrom"
                type="date"
                :max="fileActivityDateTo || undefined"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <label class="text-xs text-slate-500">Sampai</label>
              <input
                v-model="fileActivityDateTo"
                type="date"
                :min="fileActivityDateFrom || undefined"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <button
                v-if="fileActivityDateFrom || fileActivityDateTo"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-500 hover:bg-slate-50"
                @click="fileActivityDateFrom = ''; fileActivityDateTo = ''"
              >
                Reset
              </button>
            </div>
            <div class="overflow-x-auto rounded-lg border border-slate-100">
              <table class="min-w-full divide-y divide-slate-100 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  <tr>
                    <th class="px-4 py-2">Waktu</th>
                    <th class="px-4 py-2">Aksi</th>
                    <th class="px-4 py-2">Path</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-if="isFileActivityLoading">
                    <td colspan="3" class="px-4 py-6 text-center text-slate-400">Memuat data...</td>
                  </tr>
                  <tr v-else-if="fileActivity.length === 0">
                    <td colspan="3" class="px-4 py-6 text-center text-slate-400">
                      Belum ada data file activity untuk device ini. Muncul otomatis kalau ada file dibuat/diedit/dihapus di Desktop/Documents/Downloads — sekadar membuka/membaca file tidak tercatat. Kalau tetap kosong padahal ada perubahan file, cek apakah FILE_ACTIVITY_MONITOR_ENABLED aktif di .env agent.
                    </td>
                  </tr>
                  <tr v-for="row in fileActivity" v-else :key="row.id" class="hover:bg-slate-50">
                    <td class="px-4 py-2 whitespace-nowrap text-slate-500">{{ new Date(row.occurred_at).toLocaleString() }}</td>
                    <td class="px-4 py-2">
                      <span
                        class="rounded-full px-2 py-0.5 text-xs font-medium"
                        :class="{
                          'bg-emerald-100 text-emerald-700': row.event_type === 'CREATED',
                          'bg-amber-100 text-amber-700': row.event_type === 'MODIFIED',
                          'bg-red-100 text-red-700': row.event_type === 'DELETED',
                          'bg-blue-100 text-blue-700': row.event_type === 'MOVED',
                        }"
                      >
                        {{ row.event_type }}
                      </span>
                    </td>
                    <td class="px-4 py-2 font-mono text-xs text-slate-600">{{ row.path }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <Pagination
              v-if="!isFileActivityLoading && fileActivity.length > 0"
              :page="fileActivityPage.page"
              :page-size="ACTIVITY_PAGE_SIZE"
              :count="fileActivityPage.count"
              :has-previous="Boolean(fileActivityPage.previousUrl)"
              :has-next="Boolean(fileActivityPage.nextUrl)"
              @previous="goFileActivityPrevious"
              @next="goFileActivityNext"
            />
          </div>

          <div v-else-if="activeTab === 'system-errors'" class="space-y-3">
            <div class="flex items-center justify-between">
              <p class="text-xs text-slate-400">
                Error/Critical dari Windows Event Log (driver crash, hardware error, unexpected shutdown) — untuk
                diagnosis IT tanpa perlu akses fisik ke laptop. Agent sync tiap 5 menit, halaman ini auto-refresh
                tiap 20 detik.
              </p>
              <button
                class="shrink-0 rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
                @click="fetchSystemErrors"
              >
                Refresh
              </button>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <select
                v-model="systemErrorsLevelFilter"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                <option value="">Semua level</option>
                <option value="CRITICAL">Critical</option>
                <option value="ERROR">Error</option>
              </select>
              <label class="text-xs text-slate-500">Dari</label>
              <input
                v-model="systemErrorsDateFrom"
                type="date"
                :max="systemErrorsDateTo || undefined"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <label class="text-xs text-slate-500">Sampai</label>
              <input
                v-model="systemErrorsDateTo"
                type="date"
                :min="systemErrorsDateFrom || undefined"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <button
                v-if="systemErrorsLevelFilter || systemErrorsDateFrom || systemErrorsDateTo"
                class="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-500 hover:bg-slate-50"
                @click="systemErrorsLevelFilter = ''; systemErrorsDateFrom = ''; systemErrorsDateTo = ''"
              >
                Reset
              </button>
            </div>
            <div class="overflow-x-auto rounded-lg border border-slate-100">
              <table class="min-w-full divide-y divide-slate-100 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  <tr>
                    <th class="px-4 py-2">Waktu</th>
                    <th class="px-4 py-2">Level</th>
                    <th class="px-4 py-2">Log</th>
                    <th class="px-4 py-2">Provider</th>
                    <th class="px-4 py-2">Event ID</th>
                    <th class="px-4 py-2">Pesan</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-if="isSystemErrorsLoading">
                    <td colspan="6" class="px-4 py-6 text-center text-slate-400">Memuat data...</td>
                  </tr>
                  <tr v-else-if="systemErrors.length === 0">
                    <td colspan="6" class="px-4 py-6 text-center text-slate-400">
                      Belum ada data system error untuk device ini. Muncul otomatis kalau ada entri Error/Critical
                      baru di Windows Event Log — kalau tetap kosong, cek apakah SYSTEM_ERROR_MONITOR_ENABLED aktif
                      di .env agent.
                    </td>
                  </tr>
                  <tr
                    v-for="row in systemErrors"
                    v-else
                    :key="row.id"
                    class="cursor-pointer hover:bg-slate-50"
                    :class="{ 'bg-red-50/60': row.level === 'CRITICAL' }"
                    title="Klik untuk lihat detail lengkap"
                    @click="systemErrorDetail = row"
                  >
                    <td class="px-4 py-2 whitespace-nowrap text-slate-500">{{ new Date(row.occurred_at).toLocaleString() }}</td>
                    <td class="px-4 py-2">
                      <span
                        class="rounded-full px-2 py-0.5 text-xs font-semibold"
                        :class="row.level === 'CRITICAL' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'"
                      >
                        {{ row.level }}
                      </span>
                    </td>
                    <td class="px-4 py-2 text-slate-500">{{ row.log_name }}</td>
                    <td class="px-4 py-2 font-mono text-xs text-slate-600">{{ row.provider }}</td>
                    <td class="px-4 py-2 text-slate-500">{{ row.event_id }}</td>
                    <td class="px-4 py-2 max-w-md truncate text-slate-600">{{ row.message || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <Pagination
              v-if="!isSystemErrorsLoading && systemErrors.length > 0"
              :page="systemErrorsPage.page"
              :page-size="ACTIVITY_PAGE_SIZE"
              :count="systemErrorsPage.count"
              :has-previous="Boolean(systemErrorsPage.previousUrl)"
              :has-next="Boolean(systemErrorsPage.nextUrl)"
              @previous="goSystemErrorsPrevious"
              @next="goSystemErrorsNext"
            />
          </div>

          <div v-else-if="activeTab === 'audit'" class="space-y-3">
            <p class="text-xs text-slate-400">Aktivitas administratif tercatat untuk device ini (read-only).</p>
            <div class="overflow-x-auto rounded-lg border border-slate-100">
              <table class="min-w-full divide-y divide-slate-100 text-sm">
                <thead class="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  <tr>
                    <th class="px-4 py-2">Waktu</th>
                    <th class="px-4 py-2">User</th>
                    <th class="px-4 py-2">Action</th>
                    <th class="px-4 py-2">IP</th>
                    <th class="px-4 py-2">Detail</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-if="isAuditLoading">
                    <td colspan="5" class="px-4 py-6 text-center text-slate-400">Memuat data...</td>
                  </tr>
                  <tr v-else-if="auditLogs.length === 0">
                    <td colspan="5" class="px-4 py-6 text-center text-slate-400">Belum ada aktivitas tercatat untuk device ini.</td>
                  </tr>
                  <tr v-for="log in auditLogs" v-else :key="log.id" class="hover:bg-slate-50">
                    <td class="px-4 py-2 whitespace-nowrap text-slate-500">{{ new Date(log.created_at).toLocaleString() }}</td>
                    <td class="px-4 py-2 text-slate-600">{{ log.username || 'System' }}</td>
                    <td class="px-4 py-2 font-mono text-xs text-brand-700">{{ log.action }}</td>
                    <td class="px-4 py-2 text-slate-500">{{ log.ip_address || '-' }}</td>
                    <td class="px-4 py-2 text-xs text-slate-500">{{ formatAuditMetadata(log.metadata) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-else class="py-10 text-center text-sm text-slate-400">
            Tab ini tersedia di phase berikutnya sesuai roadmap.
          </div>
        </div>
      </div>
    </template>

    <ConfirmDialog
      :open="confirmOpen"
      :title="toggleAction === 'disable' ? 'Nonaktifkan device?' : 'Aktifkan kembali device?'"
      :message="`${device?.asset ? device.asset.asset_code : device?.hostname} akan di-${toggleAction === 'disable' ? 'nonaktifkan' : 'aktifkan kembali'}.`"
      :confirm-label="toggleAction === 'disable' ? 'Disable' : 'Enable'"
      :danger="toggleAction === 'disable'"
      @confirm="confirmToggle"
      @cancel="confirmOpen = false"
    />

    <div
      v-if="systemErrorDetail"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      @click.self="systemErrorDetail = null"
    >
      <div class="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <div class="flex items-start justify-between gap-3">
          <h2 class="text-base font-semibold text-slate-800">Detail System Error</h2>
          <span
            class="rounded-full px-2 py-0.5 text-xs font-semibold"
            :class="systemErrorDetail.level === 'CRITICAL' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'"
          >
            {{ systemErrorDetail.level }}
          </span>
        </div>
        <dl class="mt-4 space-y-2.5 text-sm">
          <div class="flex justify-between gap-4">
            <dt class="shrink-0 text-slate-500">Waktu</dt>
            <dd class="text-right text-slate-700">{{ new Date(systemErrorDetail.occurred_at).toLocaleString() }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="shrink-0 text-slate-500">Log</dt>
            <dd class="text-right text-slate-700">{{ systemErrorDetail.log_name }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="shrink-0 text-slate-500">Provider</dt>
            <dd class="text-right font-mono text-xs text-slate-700">{{ systemErrorDetail.provider }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="shrink-0 text-slate-500">Event ID</dt>
            <dd class="text-right text-slate-700">{{ systemErrorDetail.event_id }}</dd>
          </div>
          <div>
            <dt class="text-slate-500">Pesan lengkap</dt>
            <dd class="mt-1 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-slate-700">
              {{ systemErrorDetail.message || '-' }}
            </dd>
          </div>
        </dl>
        <div class="mt-5 flex justify-between gap-2">
          <a
            :href="systemErrorSearchUrl(systemErrorDetail)"
            target="_blank"
            rel="noopener noreferrer"
            class="rounded-md border border-brand-300 px-3 py-1.5 text-sm font-medium text-brand-700 hover:bg-brand-50"
          >
            Cari online →
          </a>
          <button
            class="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            @click="systemErrorDetail = null"
          >
            Tutup
          </button>
        </div>
      </div>
    </div>

    <!-- Modal Hasil Rotasi Token -->
    <div
      v-if="rotatedTokenInfo.open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm"
    >
      <div class="w-full max-w-md rounded-xl bg-white p-6 shadow-xl ring-1 ring-slate-900/10">
        <div class="mb-4 flex items-center gap-3">
          <div class="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div>
            <h3 class="text-base font-semibold text-slate-800">Token Berhasil Dirotasi</h3>
            <p class="text-xs text-slate-500">Device: {{ rotatedTokenInfo.deviceId }}</p>
          </div>
        </div>

        <p class="text-xs text-slate-600 mb-3">
          Token baru ini dibuat untuk menggantikan token sebelumnya. Pastikan untuk mencatat atau menyalinnya jika diperlukan:
        </p>

        <div class="relative mb-4 rounded-lg bg-slate-900 p-3 font-mono text-xs text-emerald-400 break-all select-all">
          {{ rotatedTokenInfo.token }}
        </div>

        <div class="flex justify-end gap-2">
          <button
            class="rounded-md bg-brand-600 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-700"
            @click="rotatedTokenInfo.open = false"
          >
            Selesai
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
