import api from '@/services/api'

export function getLatestMetric(deviceId) {
  return api.get(`/devices/${deviceId}/metrics/`)
}

export function getMetricHistory(deviceId, params = {}) {
  return api.get(`/devices/${deviceId}/history/`, { params })
}
