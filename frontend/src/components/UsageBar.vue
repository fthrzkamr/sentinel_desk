<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  percent: { type: Number, default: null },
  caption: { type: String, default: '' },
})

const barColor = computed(() => {
  if (props.percent === null) return 'bg-slate-300'
  if (props.percent >= 95) return 'bg-red-500'
  if (props.percent >= 80) return 'bg-amber-500'
  return 'bg-emerald-500'
})
</script>

<template>
  <div>
    <div class="flex items-baseline justify-between text-sm">
      <span class="font-medium text-slate-700">{{ label }}</span>
      <span class="text-slate-500">{{ percent === null ? 'Not Available' : `${Math.round(percent)}%` }}</span>
    </div>
    <div class="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-slate-100">
      <div
        class="h-full rounded-full transition-all duration-500"
        :class="barColor"
        :style="{ width: `${percent ?? 0}%` }"
      ></div>
    </div>
    <p v-if="caption" class="mt-1 text-xs text-slate-400">{{ caption }}</p>
  </div>
</template>
