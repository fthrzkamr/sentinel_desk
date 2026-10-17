import api from '@/services/api'

export function getSystemSettings() {
  return api.get('/settings/')
}

export function updateSystemSettings(payload) {
  return api.patch('/settings/', payload)
}
