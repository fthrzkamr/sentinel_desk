<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], required: true },
  color: { type: String, default: 'slate' }, // slate | emerald | amber | red | blue | violet
})

const colorClasses = {
  slate: 'bg-slate-100 text-slate-600',
  emerald: 'bg-emerald-100 text-emerald-600',
  amber: 'bg-amber-100 text-amber-600',
  red: 'bg-red-100 text-red-600',
  blue: 'bg-blue-100 text-blue-600',
  violet: 'bg-violet-100 text-violet-600',
}
</script>

<template>
  <div class="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-900/5 transition hover:shadow-md">
    <div class="flex items-center gap-3">
      <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg" :class="colorClasses[color]">
        <slot name="icon" />
      </div>
      <div class="min-w-0">
        <div class="truncate text-xs font-medium uppercase tracking-wide text-slate-400">{{ label }}</div>
        <div class="text-xl font-bold text-slate-800">{{ value }}</div>
      </div>
    </div>
  </div>
</template>
