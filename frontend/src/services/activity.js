import api from '@/services/api'

export function listAppUsage(params = {}) {
  return api.get('/app-usage/', { params })
}

export function listBrowsingHistory(params = {}) {
  return api.get('/browsing-history/', { params })
}

export function listFileActivity(params = {}) {
  return api.get('/file-activity/', { params })
}

export function listIdleActivity(params = {}) {
  return api.get('/idle-activity/', { params })
}

export function listSystemErrors(params = {}) {
  return api.get('/system-errors/', { params })
}
