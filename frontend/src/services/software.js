import api from '@/services/api'

export function listSoftware(params = {}) {
  return api.get('/software/', { params })
}
