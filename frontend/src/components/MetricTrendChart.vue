<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  // [{ recorded_at, cpu_percent, ram_percent, disk_percent }, ...] oldest first
  samples: { type: Array, default: () => [] },
})

// Categorical slots 1-3 from the validated default palette — this app has no
// dark mode yet, so only the light values are needed. Fixed order, never
// reassigned by filtering, per the categorical-color rule.
const SERIES = [
  { key: 'cpu_percent', label: 'CPU', color: '#2a78d6' },
  { key: 'ram_percent', label: 'RAM', color: '#eb6834' },
  { key: 'disk_percent', label: 'Disk', color: '#1baf7a' },
]

const showTable = ref(false)
const hoverIndex = ref(null)

const WIDTH = 720
const HEIGHT = 220
const PAD_LEFT = 32
const PAD_RIGHT = 12
const PAD_TOP = 12
const PAD_BOTTOM = 24
const PLOT_W = WIDTH - PAD_LEFT - PAD_RIGHT
const PLOT_H = HEIGHT - PAD_TOP - PAD_BOTTOM

const hasEnoughData = computed(() => props.samples.length >= 2)

function xFor(index) {
  const count = props.samples.length
  if (count <= 1) return PAD_LEFT
  return PAD_LEFT + (index / (count - 1)) * PLOT_W
}

function yFor(value) {
  const clamped = Math.max(0, Math.min(100, value))
  return PAD_TOP + (1 - clamped / 100) * PLOT_H
}

// Splits into separate path segments across null/missing samples instead of
// drawing a misleading straight line through a gap in the data.
function pathFor(key) {
  const segments = []
  let current = []
  props.samples.forEach((sample, index) => {
    const value = sample[key]
    if (value === null || value === undefined) {
      if (current.length) segments.push(current)
      current = []
      return
    }
    current.push(`${index === 0 || current.length === 0 ? 'M' : 'L'} ${xFor(index).toFixed(1)} ${yFor(value).toFixed(1)}`)
  })
  if (current.length) segments.push(current)
  return segments.map((seg) => seg.join(' ')).join(' ')
}

const paths = computed(() => SERIES.map((series) => ({ ...series, d: pathFor(series.key) })))

const gridLines = [0, 25, 50, 75, 100]

const hoverSample = computed(() => (hoverIndex.value === null ? null : props.samples[hoverIndex.value]))
const hoverX = computed(() => (hoverIndex.value === null ? null : xFor(hoverIndex.value)))

function handleMouseMove(event) {
  const svg = event.currentTarget
  const rect = svg.getBoundingClientRect()
  const relativeX = ((event.clientX - rect.left) / rect.width) * WIDTH
  const count = props.samples.length
  if (count === 0) return
  const ratio = Math.max(0, Math.min(1, (relativeX - PAD_LEFT) / PLOT_W))
  hoverIndex.value = Math.round(ratio * (count - 1))
}

function handleMouseLeave() {
  hoverIndex.value = null
}

function formatTime(isoString) {
  return new Date(isoString).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function lastValue(key) {
  for (let i = props.samples.length - 1; i >= 0; i -= 1) {
    const value = props.samples[i][key]
    if (value !== null && value !== undefined) return value
  }
  return null
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <div class="flex flex-wrap gap-4">
        <div v-for="series in SERIES" :key="series.key" class="flex items-center gap-1.5 text-xs">
          <span class="h-2.5 w-2.5 rounded-full" :style="{ backgroundColor: series.color }" />
          <span class="text-slate-600">{{ series.label }}</span>
          <span class="font-medium text-slate-800">
            {{ lastValue(series.key) === null ? '-' : `${Math.round(lastValue(series.key))}%` }}
          </span>
        </div>
      </div>
      <button
        class="rounded-md border border-slate-300 px-2.5 py-1 text-xs text-slate-500 hover:bg-slate-50"
        @click="showTable = !showTable"
      >
        {{ showTable ? 'Lihat grafik' : 'Lihat sebagai tabel' }}
      </button>
    </div>

    <div v-if="!hasEnoughData" class="flex h-[220px] items-center justify-center text-sm text-slate-400">
      Belum cukup data untuk menampilkan grafik tren.
    </div>

    <svg
      v-else-if="!showTable"
      :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
      class="w-full select-none"
      role="img"
      aria-label="Grafik tren CPU, RAM, dan Disk"
      @mousemove="handleMouseMove"
      @mouseleave="handleMouseLeave"
    >
      <line
        v-for="value in gridLines"
        :key="value"
        :x1="PAD_LEFT"
        :x2="WIDTH - PAD_RIGHT"
        :y1="yFor(value)"
        :y2="yFor(value)"
        stroke="#e1e0d9"
        stroke-width="1"
      />
      <text
        v-for="value in gridLines"
        :key="`label-${value}`"
        :x="PAD_LEFT - 6"
        :y="yFor(value) + 3"
        text-anchor="end"
        font-size="9"
        fill="#898781"
      >
        {{ value }}
      </text>

      <path
        v-for="series in paths"
        :key="series.key"
        :d="series.d"
        fill="none"
        :stroke="series.color"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />

      <g v-if="hoverSample">
        <line :x1="hoverX" :x2="hoverX" :y1="PAD_TOP" :y2="HEIGHT - PAD_BOTTOM" stroke="#c3c2b7" stroke-width="1" />
        <circle
          v-for="series in SERIES"
          :key="series.key"
          v-show="hoverSample[series.key] !== null && hoverSample[series.key] !== undefined"
          :cx="hoverX"
          :cy="yFor(hoverSample[series.key] ?? 0)"
          r="3"
          :fill="series.color"
          stroke="#ffffff"
          stroke-width="1.5"
        />
      </g>

      <foreignObject
        v-if="hoverSample"
        :x="Math.min(Math.max(hoverX - 70, PAD_LEFT), WIDTH - PAD_RIGHT - 140)"
        y="4"
        width="140"
        height="76"
      >
        <div xmlns="http://www.w3.org/1999/xhtml" class="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-[10px] shadow-md">
          <div class="mb-1 font-medium text-slate-700">{{ formatTime(hoverSample.recorded_at) }}</div>
          <div v-for="series in SERIES" :key="series.key" class="flex items-center justify-between gap-2 text-slate-500">
            <span class="flex items-center gap-1">
              <span class="h-1.5 w-1.5 rounded-full" :style="{ backgroundColor: series.color }" />
              {{ series.label }}
            </span>
            <span class="font-medium text-slate-700">
              {{ hoverSample[series.key] === null || hoverSample[series.key] === undefined ? '-' : `${Math.round(hoverSample[series.key])}%` }}
            </span>
          </div>
        </div>
      </foreignObject>
    </svg>

    <div v-else class="max-h-[220px] overflow-y-auto rounded-lg border border-slate-100">
      <table class="min-w-full divide-y divide-slate-100 text-xs">
        <thead class="sticky top-0 bg-slate-50 text-left font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th class="px-3 py-2">Waktu</th>
            <th v-for="series in SERIES" :key="series.key" class="px-3 py-2">{{ series.label }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="(sample, index) in [...samples].reverse()" :key="index" class="hover:bg-slate-50">
            <td class="px-3 py-1.5 text-slate-500">{{ formatTime(sample.recorded_at) }}</td>
            <td v-for="series in SERIES" :key="series.key" class="px-3 py-1.5 text-slate-700">
              {{ sample[series.key] === null || sample[series.key] === undefined ? '-' : `${Math.round(sample[series.key])}%` }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="text-xs text-slate-400">{{ samples.length }} sampel terakhir (bukan rentang kalender tetap).</p>
  </div>
</template>
