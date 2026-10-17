import api from '@/services/api'

export function listAuditLogs(params = {}) {
  return api.get('/audit-logs/', { params })
}
