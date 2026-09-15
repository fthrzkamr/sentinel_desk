import { defineStore } from 'pinia'

import api from '@/services/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    accessToken: localStorage.getItem('sd_access_token') || null,
    refreshToken: localStorage.getItem('sd_refresh_token') || null,
  }),

  getters: {
    isAuthenticated: (state) => Boolean(state.accessToken),
    permissions: (state) => state.user?.permissions || [],
  },

  actions: {
    hasPermission(code) {
      return this.permissions.includes(code)
    },

    setTokens({ access, refresh }) {
      this.accessToken = access
      this.refreshToken = refresh
      localStorage.setItem('sd_access_token', access)
      localStorage.setItem('sd_refresh_token', refresh)
    },

    async login(username, password) {
      const { data } = await api.post('/auth/login/', { username, password })
      this.setTokens({ access: data.access, refresh: data.refresh })
      this.user = data.user
      return data.user
    },

    async fetchMe() {
      const { data } = await api.get('/auth/me/')
      this.user = data
      return data
    },

    async logout() {
      try {
        if (this.refreshToken) {
          await api.post('/auth/logout/', { refresh: this.refreshToken })
        }
      } finally {
        this.user = null
        this.accessToken = null
        this.refreshToken = null
        localStorage.removeItem('sd_access_token')
        localStorage.removeItem('sd_refresh_token')
      }
    },
  },
})
