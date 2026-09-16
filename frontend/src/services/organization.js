import api from '@/services/api'

export function listCompanies(params = {}) {
  return api.get('/companies/', { params })
}

export function createCompany(payload) {
  return api.post('/companies/', payload)
}

export function listBranches(params = {}) {
  return api.get('/branches/', { params })
}

export function createBranch(payload) {
  return api.post('/branches/', payload)
}

export function listDepartments(params = {}) {
  return api.get('/departments/', { params })
}

export function createDepartment(payload) {
  return api.post('/departments/', payload)
}

export function listEmployees(params = {}) {
  return api.get('/employees/', { params })
}

export function createEmployee(payload) {
  return api.post('/employees/', payload)
}
