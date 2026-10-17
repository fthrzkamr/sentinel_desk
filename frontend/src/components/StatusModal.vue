<script setup>
import { onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  variant: { type: String, default: 'success' }, // 'success' | 'error'
  title: { type: String, required: true },
  message: { type: String, default: '' },
  autoCloseMs: { type: Number, default: 0 },
})

const emit = defineEmits(['primary', 'close'])

let autoCloseTimer = null

watch(
  () => props.open,
  (isOpen) => {
    clearTimeout(autoCloseTimer)
    if (isOpen && props.autoCloseMs > 0) {
      autoCloseTimer = setTimeout(() => emit('primary'), props.autoCloseMs)
    }
  },
)

onBeforeUnmount(() => clearTimeout(autoCloseTimer))
</script>

<template>
  <Transition name="modal-fade">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4 backdrop-blur-sm"
      @click.self="emit('close')"
    >
      <div class="modal-pop w-full max-w-sm overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div class="px-6 pb-7 pt-8 text-center">
          <div
            class="icon-pop mx-auto flex h-16 w-16 items-center justify-center rounded-full"
            :class="variant === 'success' ? 'bg-emerald-100' : 'bg-red-100'"
          >
            <svg
              v-if="variant === 'success'"
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="3"
              class="h-8 w-8 text-emerald-600"
            >
              <path class="checkmark-path" stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
            </svg>
            <svg
              v-else
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="3"
              class="h-8 w-8 text-red-600"
            >
              <path class="checkmark-path" stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>

          <h2 class="mt-4 text-lg font-semibold text-slate-800">{{ title }}</h2>
          <p v-if="message" class="mt-1.5 text-sm text-slate-500">{{ message }}</p>
        </div>

        <div v-if="autoCloseMs > 0" class="h-1 w-full bg-slate-100">
          <div
            class="progress-bar h-full"
            :class="variant === 'success' ? 'bg-emerald-500' : 'bg-red-500'"
            :style="{ animationDuration: `${autoCloseMs}ms` }"
          ></div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-pop {
  animation: modal-pop 0.25s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes modal-pop {
  from {
    opacity: 0;
    transform: scale(0.92) translateY(6px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

.icon-pop {
  animation: icon-pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) 0.1s both;
}

@keyframes icon-pop {
  from {
    opacity: 0;
    transform: scale(0.5);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.progress-bar {
  animation: progress-shrink linear forwards;
  transform-origin: left;
}

@keyframes progress-shrink {
  from {
    transform: scaleX(1);
  }
  to {
    transform: scaleX(0);
  }
}
</style>
