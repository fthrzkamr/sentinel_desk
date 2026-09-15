import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/dashboard/DashboardView.vue'),
      },
      {
        path: 'devices',
        name: 'devices',
        component: () => import('@/views/devices/DeviceListView.vue'),
        meta: { permission: 'device.view' },
      },
      {
        path: 'devices/:deviceId',
        name: 'device-detail',
        component: () => import('@/views/devices/DeviceDetailView.vue'),
        meta: { permission: 'device.view' },
      },
      {
        path: 'agents',
        name: 'agents',
        component: () => import('@/views/agents/AgentTokensView.vue'),
        meta: { permission: 'agent.manage' },
      },
      {
        path: 'software',
        name: 'software',
        component: () => import('@/views/software/SoftwareInventoryView.vue'),
        meta: { permission: 'software.view' },
      },
      {
        path: 'map',
        name: 'map',
        component: () => import('@/views/locations/MapView.vue'),
        meta: { permission: 'location.view' },
      },
      {
        path: 'alerts',
        name: 'alerts',
        component: () => import('@/views/alerts/AlertsView.vue'),
        meta: { permission: 'alert.view' },
      },
      {
        path: 'users',
        name: 'users',
        component: () => import('@/views/users/UsersView.vue'),
        meta: { permission: 'user.manage' },
      },
      {
        path: 'audit-logs',
        name: 'audit-logs',
        component: () => import('@/views/audit/AuditLogsView.vue'),
        meta: { permission: 'audit.view' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.name === 'login' && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }

  if (to.meta.permission && !auth.user && auth.isAuthenticated) {
    try {
      await auth.fetchMe()
    } catch {
      return { name: 'login' }
    }
  }

  if (to.meta.permission && !auth.hasPermission(to.meta.permission)) {
    return { name: 'dashboard' }
  }

  return true
})

export default router
