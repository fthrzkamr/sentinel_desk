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
