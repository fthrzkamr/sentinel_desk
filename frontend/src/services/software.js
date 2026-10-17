import api from '@/services/api'

export function listSoftware(params = {}) {
  return api.get('/software/', { params })
}

export function listSoftwareWhitelist() {
  return api.get('/software-whitelist/')
}

export function addSoftwareWhitelistEntry(name) {
  return api.post('/software-whitelist/', { name })
}

export function deleteSoftwareWhitelistEntry(id) {
  return api.delete(`/software-whitelist/${id}/`)
}
