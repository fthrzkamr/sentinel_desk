<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import NavIcon from '@/components/NavIcon.vue'
import { useAuthStore } from '@/stores/auth'
import { useMonitoringStore } from '@/stores/monitoring'

const auth = useAuthStore()
const monitoring = useMonitoringStore()
const router = useRouter()
const route = useRoute()

const rawNavItems = [
  { label: 'Dashboard', to: '/', icon: 'home', section: 'Menu' },
  { label: 'Devices', to: '/devices', icon: 'monitor', permission: 'device.view', section: 'Menu' },
  { label: 'Live Monitoring', to: '/live-monitoring', icon: 'activity', soon: true, section: 'Menu' },
  { label: 'Map', to: '/map', icon: 'map-pin', permission: 'location.view', section: 'Menu' },
  { label: 'Software', to: '/software', icon: 'package', permission: 'software.view', section: 'Manajemen' },
  { label: 'Alerts', to: '/alerts', icon: 'bell', permission: 'alert.view', section: 'Manajemen' },
  { label: 'History', to: '/history', icon: 'clock', permission: 'monitoring.view', section: 'Manajemen' },
  { label: 'Agents', to: '/agents', icon: 'cpu', permission: 'agent.manage', section: 'Manajemen' },
  { label: 'Users', to: '/users', icon: 'users', permission: 'user.manage', section: 'Manajemen' },
  { label: 'Audit Logs', to: '/audit-logs', icon: 'file-text', permission: 'audit.view', section: 'Sistem' },
  { label: 'Settings', to: '/settings', icon: 'sliders', permission: 'settings.manage', section: 'Sistem' },
]

const navItems = computed(() =>
  rawNavItems
    .filter((item) => !item.permission || auth.hasPermission(item.permission))
    .map((item) => ({
      ...item,
      disabled: Boolean(item.soon),
      active: item.to === '/' ? route.path === '/' : route.path.startsWith(item.to),
    })),
)

const navSections = computed(() => {
  const order = ['Menu', 'Manajemen', 'Sistem']
  return order
    .map((section) => ({ section, items: navItems.value.filter((item) => item.section === section) }))
    .filter((group) => group.items.length > 0)
})

onMounted(async () => {
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      router.push({ name: 'login' })
      return
    }
  }
  monitoring.connect()
})

onBeforeUnmount(() => {
  monitoring.disconnect()
})

async function handleLogout() {
  monitoring.disconnect()
  await auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="flex min-h-screen">
    <aside class="flex w-64 shrink-0 flex-col bg-gradient-to-b from-slate-900 via-slate-900 to-slate-950 text-slate-200">
      <div class="flex h-16 items-center justify-center border-b border-white/10">
        <img src="/logo-lockup.png" alt="SentinelDesk" class="h-14 w-auto object-contain" />
      </div>
      <nav class="flex-1 space-y-5 overflow-y-auto px-3 py-5">
        <div v-for="group in navSections" :key="group.section">
          <p class="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            {{ group.section }}
          </p>
          <div class="space-y-0.5">
            <router-link
              v-for="item in group.items"
              :key="item.label"
              :to="item.disabled ? '#' : item.to"
              class="group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition"
              :class="[
                item.disabled
                  ? 'cursor-not-allowed text-slate-500'
                  : 'text-slate-300 hover:bg-white/5 hover:text-white',
                item.active && 'bg-brand-600/90 text-white shadow-md shadow-brand-900/40 hover:bg-brand-600',
              ]"
            >
              <NavIcon
                :name="item.icon"
                :class="item.active ? 'text-white' : 'text-slate-500 group-hover:text-slate-300'"
              />
              <span class="flex-1">{{ item.label }}</span>
              <span
                v-if="item.disabled"
                class="rounded-full bg-white/5 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-500"
              >
                soon
              </span>
            </router-link>
          </div>
        </div>
      </nav>
    </aside>

    <div class="flex flex-1 flex-col">
      <header class="flex h-16 items-center justify-end border-b border-slate-200 bg-white px-6">
        <div class="flex items-center gap-3">
          <router-link
            v-if="auth.hasPermission('alert.view')"
            to="/alerts"
            class="relative rounded-md border border-slate-300 p-2 text-slate-500 transition hover:border-slate-400 hover:text-slate-700"
            title="Alerts"
          >
            <NavIcon name="bell" />
            <span
              v-if="monitoring.openAlertsCount > 0"
              class="absolute -right-1.5 -top-1.5 flex h-5 min-w-[1.25rem] items-center justify-center rounded-full px-1 text-[10px] font-semibold text-white"
              :class="monitoring.criticalAlertsCount > 0 ? 'bg-red-600' : 'bg-amber-500'"
            >
              {{ monitoring.openAlertsCount > 99 ? '99+' : monitoring.openAlertsCount }}
            </span>
          </router-link>
          <button
            class="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 transition hover:border-red-300 hover:bg-red-50 hover:text-red-600"
            @click="handleLogout"
          >
            Logout
          </button>
        </div>
      </header>

      <main class="flex-1 bg-slate-100 p-6">
        <router-view />
      </main>
    </div>
  </div>
</template>
