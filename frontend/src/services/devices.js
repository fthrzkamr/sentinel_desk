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

export function approveDevice(deviceId) {
  return api.post(`/devices/${deviceId}/approve/`)
}

export function getDeviceAssetSuggestions(deviceId) {
  return api.get(`/devices/${deviceId}/asset-suggestions/`)
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

export function listAssets(params = {}) {
  return api.get('/assets/', { params })
}

export function linkAsset(assetId, deviceId) {
  return api.post(`/assets/${assetId}/link/`, { device_id: deviceId })
}

export function setAssetUser(assetId, employeeId) {
  return api.post(`/assets/${assetId}/set-user/`, { employee_id: employeeId })
}
