import { defineStore } from 'pinia'

import { getAlertSummary } from '@/services/alerts'
import { useAuthStore } from '@/stores/auth'

// Same-origin fallback for production (one edge nginx, whatever its domain
// is) — WebSocket needs a full scheme+host unlike a relative fetch/axios
// URL, so it's built from the page's own location instead of hardcoded.
const WS_BASE_URL =
  import.meta.env.VITE_WS_BASE_URL || `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`
const RECONNECT_DELAY_MS = 3000

export const useMonitoringStore = defineStore('monitoring', {
  state: () => ({
    socket: null,
    connected: false,
    shouldReconnect: false,
    liveDevices: {}, // device_id -> { status, cpu_percent, ram_percent, disk_percent, battery_percent, battery_charging, last_seen }
    openAlertsCount: 0,
    criticalAlertsCount: 0,
  }),

  actions: {
    async fetchAlertSummary() {
      const auth = useAuthStore()
      if (!auth.hasPermission('alert.view')) return
      try {
        const { data } = await getAlertSummary()
        this.openAlertsCount = data.open
        this.criticalAlertsCount = data.open_critical
      } catch {
        // non-critical — the bell just stays at its last known count
      }
    },

    connect() {
      if (this.socket) return
      this.shouldReconnect = true

      const auth = useAuthStore()
      if (!auth.accessToken) return

      this.fetchAlertSummary()

      const socket = new WebSocket(`${WS_BASE_URL}/dashboard/?token=${auth.accessToken}`)

      socket.onopen = () => {
        this.connected = true
      }

      socket.onmessage = (event) => {
        let message
        try {
          message = JSON.parse(event.data)
        } catch {
          return
        }
        if (message.type === 'device.metric' || message.type === 'device.status_changed') {
          const payload = message.payload
          this.liveDevices[payload.device_id] = {
            ...this.liveDevices[payload.device_id],
            ...payload,
          }
        } else if (message.type === 'alert.triggered' || message.type === 'alert.updated') {
          this.fetchAlertSummary()
        }
      }

      socket.onclose = () => {
        this.connected = false
        this.socket = null
        if (this.shouldReconnect) {
          setTimeout(() => this.connect(), RECONNECT_DELAY_MS)
        }
      }

      socket.onerror = () => {
        socket.close()
      }

      this.socket = socket
    },

    disconnect() {
      this.shouldReconnect = false
      if (this.socket) {
        this.socket.close()
        this.socket = null
      }
      this.connected = false
    },
  },
})
