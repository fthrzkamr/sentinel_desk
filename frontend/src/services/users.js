import api from '@/services/api'

export function listUsers(params = {}) {
  return api.get('/users/', { params })
}

export function createUser(payload) {
  return api.post('/users/', payload)
}

export function updateUser(id, payload) {
  return api.patch(`/users/${id}/`, payload)
}

export function activateUser(id) {
  return api.post(`/users/${id}/activate/`)
}

export function deactivateUser(id) {
  return api.post(`/users/${id}/deactivate/`)
}

export function resetUserPassword(id, newPassword) {
  return api.post(`/users/${id}/reset-password/`, { new_password: newPassword })
}

export function listRoles() {
  return api.get('/roles/')
}
