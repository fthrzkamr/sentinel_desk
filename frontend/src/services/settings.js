import api from '@/services/api'

export function getSystemSettings() {
  return api.get('/settings/')
}

export function updateSystemSettings(payload) {
  return api.patch('/settings/', payload)
}

export function sendTestNotification(payload) {
  return api.post('/settings/test-notification/', payload)
}

export function uploadAgentBinary(formData) {
  return api.post('/settings/agent-binary/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
