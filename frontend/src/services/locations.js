import api from '@/services/api'

export function listLatestLocations() {
  return api.get('/locations/')
}

export function getDeviceLocationHistory(deviceId, params = {}) {
  return api.get(`/devices/${deviceId}/locations/`, { params })
}
