<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { useAuthStore } from '@/stores/auth'

const props = defineProps({
  deviceId: { type: String, required: true },
})

const WS_BASE_URL =
  import.meta.env.VITE_WS_BASE_URL || `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`

const auth = useAuthStore()

const STATE = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  STREAMING: 'streaming',
  ERROR: 'error',
}

const state = ref(STATE.IDLE)
const errorMessage = ref('')
const permissionStatus = ref('')
const videoEl = ref(null)
const screenContainerEl = ref(null)
const fullscreenContainerEl = ref(null)
const isFullscreen = ref(false)
const configuredIceServers = ref([{ urls: 'stun:stun.l.google.com:19302' }])
const monitors = ref([])
const activeMonitor = ref(1)

// Remote Control state
const isControlActive = ref(false)
const showClipboardModal = ref(false)
const clipboardInputText = ref('')
const clipboardSendFeedback = ref('')

let socket = null
let pc = null
let controlChannel = null
let lastMoveTime = 0

function cleanup() {
  if (isFullscreen.value) {
    try {
      if (document.fullscreenElement || document.webkitFullscreenElement) {
        document.exitFullscreen()
      }
    } catch {
      // ignore
    }
    isFullscreen.value = false
  }
  if (controlChannel) {
    try {
      controlChannel.close()
    } catch {
      // ignore
    }
    controlChannel = null
  }
  if (pc) {
    pc.close()
    pc = null
  }
  if (socket) {
    socket.onclose = null
    socket.close()
    socket = null
  }
  if (videoEl.value) {
    videoEl.value.srcObject = null
  }
  monitors.value = []
  isControlActive.value = false
  showClipboardModal.value = false
  permissionStatus.value = ''
}

async function toggleFullscreen() {
  const el = fullscreenContainerEl.value
  if (!el) return

  if (!isFullscreen.value) {
    isFullscreen.value = true
    try {
      if (el.requestFullscreen) {
        await el.requestFullscreen()
      } else if (el.webkitRequestFullscreen) {
        await el.webkitRequestFullscreen()
      }
    } catch {
      // In-page maximize handled via isFullscreen = true
    }
  } else {
    isFullscreen.value = false
    try {
      if (document.fullscreenElement || document.webkitFullscreenElement) {
        if (document.exitFullscreen) {
          await document.exitFullscreen()
        } else if (document.webkitExitFullscreen) {
          await document.webkitExitFullscreen()
        }
      }
    } catch {
      // ignore
    }
  }
}

function onFullscreenChange() {
  if (!document.fullscreenElement && !document.webkitFullscreenElement) {
    isFullscreen.value = false
  }
}

function stop() {
  cleanup()
  state.value = STATE.IDLE
  errorMessage.value = ''
}

function switchMonitor(index) {
  activeMonitor.value = index
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'switch_monitor', monitor_index: index }))
  }
}

function toggleControl() {
  isControlActive.value = !isControlActive.value
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'remote_control_toggle', enabled: isControlActive.value }))
  }
  if (isControlActive.value && screenContainerEl.value) {
    screenContainerEl.value.focus()
  }
}

function sendControlEvent(event) {
  if (!isControlActive.value) return
  let sent = false
  try {
    const payload = JSON.stringify(event)
    if (controlChannel && controlChannel.readyState === 'open') {
      controlChannel.send(payload)
      sent = true
    }
  } catch (err) {
    // DataChannel send failed, fall back to WebSocket
  }

  if (!sent) {
    try {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'remote_input', event }))
      }
    } catch (err) {
      // Ignore transient network errors
    }
  }
}

function sendShortcut(shortcut) {
  sendControlEvent({ action: 'shortcut', shortcut })
}

function sendClipboardText() {
  if (!clipboardInputText.value) return
  sendControlEvent({ action: 'set_clipboard', text: clipboardInputText.value })
  clipboardSendFeedback.value = 'Teks berhasil disalin ke clipboard target!'
  setTimeout(() => {
    clipboardSendFeedback.value = ''
    showClipboardModal.value = false
    clipboardInputText.value = ''
  }, 1000)
}

function sendTypeText() {
  if (!clipboardInputText.value) return
  sendControlEvent({ action: 'type_text', text: clipboardInputText.value })
  clipboardSendFeedback.value = 'Teks berhasil diketik ke target!'
  setTimeout(() => {
    clipboardSendFeedback.value = ''
    showClipboardModal.value = false
    clipboardInputText.value = ''
  }, 1000)
}

function getNormalizedCoordinates(e) {
  const video = videoEl.value
  if (!video || !video.videoWidth || !video.videoHeight) return null

  const rect = video.getBoundingClientRect()
  const videoRatio = video.videoWidth / video.videoHeight
  const elementRatio = rect.width / rect.height

  let renderWidth = rect.width
  let renderHeight = rect.height
  let offsetX = 0
  let offsetY = 0

  if (elementRatio > videoRatio) {
    // Pillarboxed (bars on left/right)
    renderWidth = rect.height * videoRatio
    offsetX = (rect.width - renderWidth) / 2
  } else {
    // Letterboxed (bars on top/bottom)
    renderHeight = rect.width / videoRatio
    offsetY = (rect.height - renderHeight) / 2
  }

  const clientX = e.clientX - rect.left - offsetX
  const clientY = e.clientY - rect.top - offsetY

  if (clientX < 0 || clientX > renderWidth || clientY < 0 || clientY > renderHeight) {
    return null
  }

  return {
    x: Math.max(0, Math.min(1, clientX / renderWidth)),
    y: Math.max(0, Math.min(1, clientY / renderHeight)),
  }
}

function handleMouseMove(e) {
  if (!isControlActive.value) return
  const now = Date.now()
  if (now - lastMoveTime < 30) return // Throttle to ~33 FPS
  lastMoveTime = now

  const coords = getNormalizedCoordinates(e)
  if (coords) {
    sendControlEvent({ action: 'mouse_move', x: coords.x, y: coords.y })
  }
}

function handleMouseDown(e) {
  if (!isControlActive.value) return
  e.preventDefault()
  if (screenContainerEl.value) {
    screenContainerEl.value.focus()
  }

  const coords = getNormalizedCoordinates(e)
  if (coords) {
    sendControlEvent({ action: 'mouse_down', button: e.button, x: coords.x, y: coords.y })
  }
}

function handleMouseUp(e) {
  if (!isControlActive.value) return
  e.preventDefault()
  const coords = getNormalizedCoordinates(e)
  if (coords) {
    sendControlEvent({ action: 'mouse_up', button: e.button, x: coords.x, y: coords.y })
  }
}

function handleContextMenu(e) {
  if (isControlActive.value) {
    e.preventDefault()
  }
}

function handleWheel(e) {
  if (!isControlActive.value) return
  e.preventDefault()
  sendControlEvent({ action: 'mouse_wheel', delta_y: e.deltaY, delta_x: e.deltaX })
}

function handleDoubleClick(e) {
  if (!isControlActive.value) return
  e.preventDefault()
  const coords = getNormalizedCoordinates(e)
  if (coords) {
    sendControlEvent({ action: 'mouse_double_click', x: coords.x, y: coords.y })
  }
}

function handleKeyDown(e) {
  if (e.key === 'Escape' && isFullscreen.value && !isControlActive.value) {
    toggleFullscreen()
    return
  }

  if (!isControlActive.value) return

  // Prevent browser shortcuts from stealing focus
  const intercepted = ['Tab', 'Alt', 'ContextMenu', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']
  if (intercepted.includes(e.key) || (e.key === 'Backspace' && e.target !== document.querySelector('input, textarea'))) {
    e.preventDefault()
  }

  sendControlEvent({ action: 'key_down', key: e.key, code: e.code })
}

function handleKeyUp(e) {
  if (!isControlActive.value) return
  sendControlEvent({ action: 'key_up', key: e.key, code: e.code })
}

async function start() {
  state.value = STATE.CONNECTING
  errorMessage.value = ''
  permissionStatus.value = 'Menghubungkan ke perangkat...'
  isControlActive.value = false

  socket = new WebSocket(`${WS_BASE_URL}/livescreen/${props.deviceId}/?token=${auth.accessToken}`)

  socket.onopen = () => {
    pc = new RTCPeerConnection({
      iceServers: configuredIceServers.value,
    })

    // Create bidirectional DataChannel for remote input
    try {
      controlChannel = pc.createDataChannel('control', { ordered: true })
      controlChannel.onopen = () => {
        console.log('WebRTC control channel open')
      }
    } catch (err) {
      console.warn('Could not create WebRTC data channel:', err)
    }

    pc.ontrack = (event) => {
      if (videoEl.value && event.streams[0]) {
        videoEl.value.srcObject = event.streams[0]
      }
      if (event.track && 'contentHint' in event.track) {
        event.track.contentHint = 'detail'
      }
      state.value = STATE.STREAMING
    }

    let disconnectTimer = null
    pc.onconnectionstatechange = () => {
      if (!pc) return
      if (pc.connectionState === 'connected') {
        if (disconnectTimer) {
          clearTimeout(disconnectTimer)
          disconnectTimer = null
        }
      } else if (pc.connectionState === 'disconnected') {
        if (!disconnectTimer) {
          disconnectTimer = setTimeout(() => {
            if (pc && pc.connectionState === 'disconnected' && state.value === STATE.STREAMING) {
              errorMessage.value = 'Koneksi live screen terputus.'
              stop()
            }
          }, 4000)
        }
      } else if (['failed', 'closed'].includes(pc.connectionState) && state.value === STATE.STREAMING) {
        errorMessage.value = 'Koneksi live screen terputus.'
        stop()
      }
    }

    pc.addTransceiver('video', { direction: 'recvonly' })

    createAndSendOffer()
  }

  socket.onmessage = async (event) => {
    let message
    try {
      message = JSON.parse(event.data)
    } catch {
      return
    }

    if (message.type === 'permission_pending') {
      state.value = STATE.CONNECTING
      permissionStatus.value = message.message || 'Menunggu persetujuan pengguna laptop klien...'
    } else if (message.type === 'permission_granted') {
      permissionStatus.value = 'Izin disetujui, memulai sesi streaming...'
    } else if (message.type === 'permission_denied') {
      errorMessage.value = message.message || 'Permintaan remote ditolak oleh pengguna perangkat.'
      state.value = STATE.ERROR
      cleanup()
    } else if (message.type === 'ice_config' && Array.isArray(message.ice_servers)) {
      configuredIceServers.value = message.ice_servers
    } else if (message.type === 'monitors_list' && Array.isArray(message.monitors)) {
      monitors.value = message.monitors
      if (message.active_monitor !== undefined) {
        activeMonitor.value = message.active_monitor
      }
    } else if (message.type === 'monitor_switched') {
      activeMonitor.value = message.active_monitor
    } else if (message.type === 'webrtc_answer') {
      await pc.setRemoteDescription({ type: 'answer', sdp: message.sdp })
    } else if (message.type === 'error') {
      errorMessage.value = message.message || 'Live screen tidak dapat dimulai.'
      state.value = STATE.ERROR
      cleanup()
    } else if (message.type === 'agent_disconnected') {
      errorMessage.value = 'Agent pada device ini terputus.'
      state.value = STATE.ERROR
      cleanup()
    }
  }

  socket.onerror = () => {
    errorMessage.value = 'Gagal terhubung ke server.'
    state.value = STATE.ERROR
  }

  socket.onclose = () => {
    if (state.value !== STATE.ERROR) {
      state.value = STATE.IDLE
    }
  }
}

async function createAndSendOffer() {
  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)
  await waitIceGatheringComplete(pc)
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'webrtc_offer', sdp: pc.localDescription.sdp }))
  }
}

function waitIceGatheringComplete(connection) {
  if (connection.iceGatheringState === 'complete') return Promise.resolve()
  return new Promise((resolve) => {
    let finished = false
    const done = () => {
      if (!finished) {
        finished = true
        connection.removeEventListener('icegatheringstatechange', check)
        clearTimeout(timer)
        resolve()
      }
    }
    const timer = setTimeout(done, 2500)
    function check() {
      if (connection.iceGatheringState === 'complete') {
        done()
      }
    }
    connection.addEventListener('icegatheringstatechange', check)
  })
}

onMounted(() => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('webkitfullscreenchange', onFullscreenChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('webkitfullscreenchange', onFullscreenChange)
  cleanup()
})

defineExpose({ STATE })
</script>

<template>
  <div
    ref="fullscreenContainerEl"
    :class="
      isFullscreen
        ? 'fixed inset-0 z-50 flex flex-col bg-slate-950 p-4 space-y-3 overflow-hidden'
        : 'space-y-3'
    "
  >
    <!-- Header Controls -->
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2 text-sm">
        <span
          class="h-2 w-2 rounded-full"
          :class="{
            'bg-slate-300': state === STATE.IDLE,
            'bg-amber-400 animate-pulse': state === STATE.CONNECTING,
            'bg-emerald-500': state === STATE.STREAMING,
            'bg-red-500': state === STATE.ERROR,
          }"
        />
        <span :class="isFullscreen ? 'text-slate-200 font-medium' : 'text-slate-500 font-medium'">
          {{
            {
              idle: 'Tidak aktif',
              connecting: permissionStatus || 'Menghubungkan...',
              streaming: 'Streaming aktif',
              error: 'Error',
            }[state]
          }}
        </span>
      </div>

      <div class="flex items-center gap-2">
        <!-- Monitor Selector -->
        <div v-if="state === STATE.STREAMING && monitors.length > 1" class="flex items-center gap-1.5">
          <label class="text-xs font-medium" :class="isFullscreen ? 'text-slate-300' : 'text-slate-500'">Layar:</label>
          <select
            v-model="activeMonitor"
            class="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            @change="switchMonitor(activeMonitor)"
          >
            <option v-for="m in monitors" :key="m.index" :value="m.index">
              {{ m.name }}
            </option>
          </select>
        </div>

        <!-- Toggle Remote Control Mode -->
        <button
          v-if="state === STATE.STREAMING"
          type="button"
          class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all shadow-sm"
          :class="
            isControlActive
              ? 'bg-amber-500 text-white hover:bg-amber-600 ring-2 ring-amber-300 animate-pulse'
              : 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
          "
          @click="toggleControl"
        >
          <span v-if="isControlActive">Kendali Aktif</span>
          <span v-else>Ambil Kendali (Remote)</span>
        </button>

        <!-- Toggle Fullscreen / Minimize -->
        <button
          v-if="state === STATE.STREAMING"
          type="button"
          class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 transition-all"
          @click="toggleFullscreen"
        >
          {{ isFullscreen ? 'Perkecil (Minimize)' : 'Layar Penuh (Full)' }}
        </button>

        <!-- Start / Stop buttons -->
        <button
          v-if="state === STATE.IDLE || state === STATE.ERROR"
          class="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 shadow-sm"
          @click="start"
        >
          Mulai Live Screen
        </button>
        <button
          v-else
          class="rounded-lg bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700 shadow-sm"
          @click="stop"
        >
          Hentikan
        </button>
      </div>
    </div>

    <!-- Error Banner -->
    <div v-if="errorMessage" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
      {{ errorMessage }}
    </div>

    <!-- Quick Shortcuts Toolbar (Shown when Remote Control is Active) -->
    <div
      v-if="state === STATE.STREAMING && isControlActive"
      class="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-800 p-2 text-xs text-white shadow-inner"
    >
      <div class="flex items-center gap-1.5 font-medium text-amber-400">
        <span>Pintasan Cepat:</span>
      </div>

      <div class="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          class="rounded bg-slate-700 px-2 py-1 font-mono hover:bg-slate-600 active:bg-slate-500"
          title="Buka dialog Run Windows"
          @click="sendShortcut('win_r')"
        >
          Win + R
        </button>
        <button
          type="button"
          class="rounded bg-slate-700 px-2 py-1 font-mono hover:bg-slate-600 active:bg-slate-500"
          title="Tampilkan Desktop"
          @click="sendShortcut('win_d')"
        >
          Win + D
        </button>
        <button
          type="button"
          class="rounded bg-slate-700 px-2 py-1 font-mono hover:bg-slate-600 active:bg-slate-500"
          title="Pindah Jendela Aplikasi"
          @click="sendShortcut('alt_tab')"
        >
          Alt + Tab
        </button>
        <button
          type="button"
          class="rounded bg-slate-700 px-2 py-1 font-mono hover:bg-slate-600 active:bg-slate-500"
          title="Buka Task Manager"
          @click="sendShortcut('task_mgr')"
        >
          Ctrl + Shift + Esc
        </button>
        <button
          type="button"
          class="flex items-center gap-1 rounded bg-brand-600 px-2.5 py-1 font-medium text-white hover:bg-brand-500"
          @click="showClipboardModal = true"
        >
          Kirim Teks / Clipboard
        </button>
      </div>
    </div>

    <!-- Screen Video Area with Interactive Events -->
    <div
      ref="screenContainerEl"
      tabindex="0"
      class="relative overflow-hidden rounded-lg bg-slate-900 outline-none transition-all flex items-center justify-center"
      :class="[
        isControlActive
          ? 'ring-2 ring-amber-500 cursor-crosshair'
          : 'cursor-default',
        isFullscreen ? 'flex-1 min-h-0 w-full' : ''
      ]"
      :style="isFullscreen ? 'width: 100%; height: 100%;' : 'aspect-ratio: 16 / 9;'"
      @mousemove="handleMouseMove"
      @mousedown="handleMouseDown"
      @mouseup="handleMouseUp"
      @contextmenu="handleContextMenu"
      @wheel="handleWheel"
      @dblclick="handleDoubleClick"
      @keydown="handleKeyDown"
      @keyup="handleKeyUp"
    >
      <!-- Remote Control Status Banner Overlay -->
      <div
        v-if="state === STATE.STREAMING"
        class="absolute top-2 left-2 z-10 flex items-center gap-1.5 rounded-full bg-slate-900/80 px-2.5 py-1 text-[11px] backdrop-blur font-medium text-white shadow pointer-events-none"
      >
        <span
          class="h-2 w-2 rounded-full"
          :class="isControlActive ? 'bg-amber-400 animate-ping' : 'bg-emerald-400'"
        />
        <span>
          {{ isControlActive ? 'KENDALI AKTIF (Klik area untuk ketik)' : 'MODE PANTAU (Hanya Melihat)' }}
        </span>
      </div>

      <video
        v-show="state === STATE.STREAMING"
        ref="videoEl"
        autoplay
        playsinline
        muted
        class="h-full w-full object-contain pointer-events-none"
        style="image-rendering: -webkit-optimize-contrast; image-rendering: crisp-edges;"
      />

      <div v-if="state === STATE.CONNECTING" class="flex flex-col items-center justify-center p-6 text-center space-y-3">
        <div class="h-8 w-8 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
        <div class="text-sm font-semibold text-amber-300">
          {{ permissionStatus || 'Menunggu persetujuan pengguna laptop klien...' }}
        </div>
        <div class="text-xs text-slate-400 max-w-sm">
          Dialog konfirmasi sedang ditampilkan pada laptop klien. Pengguna dapat memilih <b>Setujui</b> untuk mengizinkan atau <b>Tolak</b>.
        </div>
      </div>
      <div v-else-if="state !== STATE.STREAMING" class="flex h-full items-center justify-center text-sm text-slate-400">
        Klik "Mulai Live Screen" untuk memulai.
      </div>
    </div>

    <p v-if="!isFullscreen" class="text-xs text-slate-400">
      Streaming & kendali remote berjalan langsung secara aman (P2P WebRTC). Setiap aktivasi kendali dicatat pada audit log.
    </p>

    <!-- Modal Kirim Teks / Clipboard -->
    <div
      v-if="showClipboardModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
    >
      <div class="w-full max-w-md rounded-xl bg-white p-5 shadow-2xl space-y-4">
        <div class="flex items-center justify-between border-b pb-3">
          <h3 class="font-semibold text-slate-800">Kirim Teks ke Laptop Klien</h3>
          <button
            type="button"
            class="text-slate-400 hover:text-slate-600"
            @click="showClipboardModal = false"
          >
            ✕
          </button>
        </div>

        <div>
          <label class="block text-xs font-medium text-slate-600 mb-1">
            Ketik atau tempel (paste) teks/password di bawah ini:
          </label>
          <textarea
            v-model="clipboardInputText"
            rows="3"
            class="w-full rounded-lg border border-slate-300 p-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            placeholder="Ketik teks yang ingin dikirimkan..."
          />
        </div>

        <div v-if="clipboardSendFeedback" class="text-xs text-emerald-600 font-medium">
          {{ clipboardSendFeedback }}
        </div>

        <div class="flex items-center justify-end gap-2 pt-2 border-t">
          <button
            type="button"
            class="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            @click="showClipboardModal = false"
          >
            Batal
          </button>
          <button
            type="button"
            class="rounded-lg bg-slate-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
            @click="sendTypeText"
          >
            Ketik Langsung
          </button>
          <button
            type="button"
            class="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700"
            @click="sendClipboardText"
          >
            Salin ke Clipboard Klien
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
