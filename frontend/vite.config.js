import path from 'node:path'
import { fileURLToPath } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [vue()],
  envDir: path.resolve(__dirname, '..'),
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    watch: {
      // Docker Desktop on Windows doesn't reliably forward inotify events
      // across a bind mount, so fall back to polling for hot-reload to work.
      usePolling: true,
    },
    // Vite rejects requests whose Host header it doesn't recognize (blocks
    // DNS-rebinding attacks) — needed to reach the dev server through an
    // ngrok tunnel. The leading dot covers every ngrok-free.dev subdomain,
    // since the free tier hands out a new random one on each restart.
    allowedHosts: ['.ngrok-free.dev'],
    // The browser calls relative /api and /ws paths (see src/services/api.js
    // and src/stores/monitoring.js) so it always targets whatever origin
    // actually served the page — localhost:5173 normally, or a tunnel
    // domain like ngrok — instead of a hardcoded localhost:8000 that only
    // ever resolves on this machine. Vite proxies those same-origin
    // requests on to the backend container over the internal Docker
    // network, WebSocket upgrades included.
    proxy: {
      '/api': { target: 'http://backend:8000', changeOrigin: true },
      '/ws': { target: 'http://backend:8000', ws: true, changeOrigin: true },
    },
  },
})
