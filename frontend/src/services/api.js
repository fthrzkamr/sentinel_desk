import axios from 'axios'

import { useAuthStore } from '@/stores/auth'

// Falls back to a same-origin relative path — correct in production where
// one edge nginx serves the frontend and proxies /api to the backend on the
// same domain, whatever that domain ends up being. Local dev always sets
// VITE_API_BASE_URL explicitly (frontend and backend run on different ports).
const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'

const api = axios.create({ baseURL })

let refreshPromise = null

api.interceptors.request.use((config) => {
  const access = localStorage.getItem('sd_access_token')
  if (access) {
    config.headers.Authorization = `Bearer ${access}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { config, response } = error
    const isAuthEndpoint = config?.url?.includes('/auth/login') || config?.url?.includes('/auth/refresh')

    if (response?.status === 401 && !config._retry && !isAuthEndpoint) {
      config._retry = true
      const refresh = localStorage.getItem('sd_refresh_token')
      if (!refresh) {
        return Promise.reject(error)
      }

      try {
        if (!refreshPromise) {
          refreshPromise = axios
            .post(`${baseURL}/auth/refresh/`, { refresh })
            .finally(() => {
              refreshPromise = null
            })
        }
        const { data } = await refreshPromise
        // Backend has ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION on
        // (see SIMPLE_JWT in settings) - every refresh call invalidates the
        // refresh token just used and issues a new one in this same
        // response. Saving only `data.access` and discarding `data.refresh`
        // meant the NEXT refresh (~15 min later, when the access token
        // expires again) kept retrying with that same now-blacklisted
        // refresh token, failed, and force-logged the user out - the
        // "logs out on its own sometimes" bug, happening like clockwork
        // roughly every 2 access-token lifetimes of active use.
        // setTokens() (not setAccessToken()) keeps the Pinia store in sync
        // too — components that build a WebSocket URL straight off
        // auth.accessToken (LiveScreenPanel, the dashboard socket) read the
        // store's reactive copy, not localStorage, so a refresh that only
        // touched localStorage left them stuck on the old, now-expired
        // token until a full page reload.
        useAuthStore().setTokens({ access: data.access, refresh: data.refresh })
        config.headers.Authorization = `Bearer ${data.access}`
        return api(config)
      } catch (refreshError) {
        localStorage.removeItem('sd_access_token')
        localStorage.removeItem('sd_refresh_token')
        window.location.href = '/login'
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  },
)

export default api
