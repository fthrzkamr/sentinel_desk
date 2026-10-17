<script setup>
import { computed } from 'vue'

const props = defineProps({
  page: { type: Number, required: true },
  pageSize: { type: Number, required: true },
  count: { type: Number, required: true },
  hasPrevious: { type: Boolean, default: false },
  hasNext: { type: Boolean, default: false },
})

defineEmits(['previous', 'next'])

const rangeStart = computed(() => (props.count === 0 ? 0 : (props.page - 1) * props.pageSize + 1))
const rangeEnd = computed(() => Math.min(props.page * props.pageSize, props.count))
</script>

<template>
  <div class="flex flex-col items-center gap-3 text-sm text-slate-500 sm:flex-row sm:justify-between">
    <span>Menampilkan {{ rangeStart }}–{{ rangeEnd }} dari {{ count }} data</span>
    <div class="flex items-center gap-2">
      <button
        class="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
        :disabled="!hasPrevious"
        @click="$emit('previous')"
      >
        Previous
      </button>
      <span class="px-1 text-xs text-slate-400">Halaman {{ page }}</span>
      <button
        class="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
        :disabled="!hasNext"
        @click="$emit('next')"
      >
        Next
      </button>
    </div>
  </div>
</template>
