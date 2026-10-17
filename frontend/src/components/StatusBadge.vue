<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, required: true },
})

const styles = {
  ONLINE: 'bg-emerald-100 text-emerald-700',
  OFFLINE: 'bg-slate-200 text-slate-600',
  WARNING: 'bg-amber-100 text-amber-700',
  CRITICAL: 'bg-red-100 text-red-700',
  DISABLED: 'bg-slate-300 text-slate-500 line-through',
}

const classes = computed(() => styles[props.status] || 'bg-slate-200 text-slate-600')
</script>

<template>
  <span class="inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="classes">
    {{ status }}
  </span>
</template>
