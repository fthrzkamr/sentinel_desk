import api from '@/services/api'

export function listDevices(params = {}) {
  return api.get('/devices/', { params })
}

export function getDevice(deviceId) {
  return api.get(`/devices/${deviceId}/`)
}

export function updateDeviceOrgAssignment(deviceId, payload) {
  return api.patch(`/devices/${deviceId}/`, payload)
}

export function disableDevice(deviceId) {
  return api.post(`/devices/${deviceId}/disable/`)
}

export function enableDevice(deviceId) {
  return api.post(`/devices/${deviceId}/enable/`)
}

export function listEnrollmentTokens() {
  return api.get('/agent/enrollment-tokens/')
}

export function createEnrollmentToken(payload) {
  return api.post('/agent/enrollment-tokens/', payload)
}

export function revokeEnrollmentToken(id) {
  return api.post(`/agent/enrollment-tokens/${id}/revoke/`)
}

export function listAgentReleases() {
  return api.get('/agent-releases/')
}

export function uploadAgentRelease({ version, notes, isActive, file }) {
  const formData = new FormData()
  formData.append('version', version)
  formData.append('notes', notes || '')
  formData.append('is_active', isActive)
  formData.append('exe_file', file)
  return api.post('/agent-releases/', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
}

export function activateAgentRelease(id) {
  return api.patch(`/agent-releases/${id}/`, { is_active: true })
}

export function deleteAgentRelease(id) {
  return api.delete(`/agent-releases/${id}/`)
}
