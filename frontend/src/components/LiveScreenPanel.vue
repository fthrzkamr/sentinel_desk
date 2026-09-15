<script setup>
import { onBeforeUnmount, ref } from 'vue'

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
const videoEl = ref(null)

let socket = null
let pc = null

function cleanup() {
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
}

function stop() {
  cleanup()
  state.value = STATE.IDLE
  errorMessage.value = ''
}

async function start() {
  state.value = STATE.CONNECTING
  errorMessage.value = ''

  socket = new WebSocket(`${WS_BASE_URL}/livescreen/${props.deviceId}/?token=${auth.accessToken}`)

  socket.onopen = () => {
    pc = new RTCPeerConnection({
      iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
    })

    pc.ontrack = (event) => {
      if (videoEl.value) {
        videoEl.value.srcObject = event.streams[0]
      }
      state.value = STATE.STREAMING
    }

    pc.onconnectionstatechange = () => {
      if (pc && ['failed', 'closed', 'disconnected'].includes(pc.connectionState) && state.value === STATE.STREAMING) {
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

    if (message.type === 'webrtc_answer') {
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
    function check() {
      if (connection.iceGatheringState === 'complete') {
        connection.removeEventListener('icegatheringstatechange', check)
        resolve()
      }
    }
    connection.addEventListener('icegatheringstatechange', check)
  })
}

onBeforeUnmount(() => {
  cleanup()
})

defineExpose({ STATE })
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
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
        <span class="text-slate-500">
          {{
            {
              idle: 'Tidak aktif',
              connecting: 'Menghubungkan...',
              streaming: 'Streaming aktif',
              error: 'Error',
            }[state]
          }}
        </span>
      </div>
      <button
        v-if="state === STATE.IDLE || state === STATE.ERROR"
        class="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
        @click="start"
      >
        Mulai Live Screen
      </button>
      <button
        v-else
        class="rounded-lg bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700"
        @click="stop"
      >
        Hentikan
      </button>
    </div>

    <div v-if="errorMessage" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
      {{ errorMessage }}
    </div>

    <div class="overflow-hidden rounded-lg bg-slate-900" style="aspect-ratio: 16 / 9">
      <video
        v-show="state === STATE.STREAMING"
        ref="videoEl"
        autoplay
        playsinline
        muted
        class="h-full w-full object-contain"
      />
      <div v-if="state !== STATE.STREAMING" class="flex h-full items-center justify-center text-sm text-slate-400">
        {{ state === STATE.CONNECTING ? 'Menunggu koneksi dari agent...' : 'Klik "Mulai Live Screen" untuk memulai.' }}
      </div>
    </div>

    <p class="text-xs text-slate-400">
      Streaming hanya berjalan selama sesi ini aktif. Device yang dipantau akan menampilkan notifikasi bahwa
      layarnya sedang diawasi. Setiap sesi tercatat pada audit log.
    </p>
  </div>
</template>
