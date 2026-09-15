import api from '@/services/api'

export function listDevices(params = {}) {
  return api.get('/devices/', { params })
}

export function getDevice(deviceId) {
  return api.get(`/devices/${deviceId}/`)
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
