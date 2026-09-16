import api from '@/services/api'

export function listCompanies(params = {}) {
  return api.get('/companies/', { params })
}

export function createCompany(payload) {
  return api.post('/companies/', payload)
}

export function deleteCompany(id) {
  return api.delete(`/companies/${id}/`)
}

export function listBranches(params = {}) {
  return api.get('/branches/', { params })
}

export function createBranch(payload) {
  return api.post('/branches/', payload)
}

export function deleteBranch(id) {
  return api.delete(`/branches/${id}/`)
}

export function listDepartments(params = {}) {
  return api.get('/departments/', { params })
}

export function createDepartment(payload) {
  return api.post('/departments/', payload)
}

export function deleteDepartment(id) {
  return api.delete(`/departments/${id}/`)
}

export function listEmployees(params = {}) {
  return api.get('/employees/', { params })
}

export function createEmployee(payload) {
  return api.post('/employees/', payload)
}

export function deleteEmployee(id) {
  return api.delete(`/employees/${id}/`)
}
