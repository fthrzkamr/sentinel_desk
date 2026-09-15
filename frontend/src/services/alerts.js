import api from '@/services/api'

export function listAlerts(params = {}) {
  return api.get('/alerts/', { params })
}

export function getAlertSummary() {
  return api.get('/alerts/summary/')
}

export function acknowledgeAlert(id) {
  return api.post(`/alerts/${id}/acknowledge/`)
}

export function resolveAlert(id) {
  return api.post(`/alerts/${id}/resolve/`)
}
