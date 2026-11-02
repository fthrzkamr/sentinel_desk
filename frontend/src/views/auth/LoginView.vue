<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import StatusModal from '@/components/StatusModal.vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const form = reactive({ username: '', password: '', otp: '' })
const isSubmitting = ref(false)
const showPassword = ref(false)
const step = ref('credentials') // 'credentials' | '2fa'
const preAuthToken = ref('')

const modal = reactive({
  open: false,
  variant: 'success',
  title: '',
  message: '',
})

function closeModal() {
  modal.open = false
}

function goToDestination() {
  modal.open = false
  router.push(route.query.redirect || { name: 'dashboard' })
}

async function handleSubmit() {
  isSubmitting.value = true
  try {
    if (step.value === 'credentials') {
      const res = await auth.login(form.username, form.password)
      if (res?.requires_2fa) {
        step.value = '2fa'
        preAuthToken.value = res.pre_auth_token
        form.otp = ''
        return
      }
      modal.variant = 'success'
      modal.title = 'Login Berhasil'
      modal.message = `Selamat datang kembali, ${res.username}.`
      modal.open = true
    } else {
      const user = await auth.login2FA(preAuthToken.value, form.otp)
      modal.variant = 'success'
      modal.title = 'Login Berhasil'
      modal.message = `Selamat datang kembali, ${user.username}.`
      modal.open = true
    }
  } catch (error) {
    modal.variant = 'error'
    modal.title = step.value === '2fa' ? 'Verifikasi 2FA Gagal' : 'Login Gagal'
    modal.message =
      error.response?.data?.detail ||
      error.response?.data?.non_field_errors?.[0] ||
      (step.value === '2fa'
        ? 'Kode OTP 2FA tidak valid atau telah kedaluwarsa.'
        : 'Username atau password salah. Silakan coba lagi.')
    modal.open = true
  } finally {
    isSubmitting.value = false
  }
}

function cancel2FA() {
  step.value = 'credentials'
  form.otp = ''
  preAuthToken.value = ''
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-slate-50 px-4">
    <div class="w-full max-w-sm">
      <div class="mb-6 text-center">
        <img src="/logo.png" alt="SentinelDesk" class="mx-auto h-28 w-28 object-contain" />
        <p class="mt-1 text-sm text-slate-500">IT Endpoint Monitoring &amp; Device Management</p>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white p-7 shadow-sm">
        <form class="space-y-4" @submit.prevent="handleSubmit">
          <template v-if="step === 'credentials'">
            <div>
              <label class="mb-1.5 block text-sm font-medium text-slate-700" for="username">Username</label>
              <div class="relative">
                <span class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-4 w-4">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
                  </svg>
                </span>
                <input
                  id="username"
                  v-model="form.username"
                  type="text"
                  required
                  autocomplete="username"
                  placeholder="cth. admin"
                  class="w-full rounded-lg border border-slate-300 py-2.5 pl-10 pr-3 text-sm transition focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </div>
            </div>

            <div>
              <label class="mb-1.5 block text-sm font-medium text-slate-700" for="password">Password</label>
              <div class="relative">
                <span class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-4 w-4">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
                  </svg>
                </span>
                <input
                  id="password"
                  v-model="form.password"
                  :type="showPassword ? 'text' : 'password'"
                  required
                  autocomplete="current-password"
                  placeholder="••••••••"
                  class="w-full rounded-lg border border-slate-300 py-2.5 pl-10 pr-10 text-sm transition focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
                <button
                  type="button"
                  class="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-600"
                  tabindex="-1"
                  @click="showPassword = !showPassword"
                >
                  <svg v-if="showPassword" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-4 w-4">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                  </svg>
                  <svg v-else xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-4 w-4">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </button>
              </div>
            </div>

            <button
              type="submit"
              :disabled="isSubmitting"
              class="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <svg v-if="isSubmitting" class="h-4 w-4 animate-spin text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"></path>
              </svg>
              {{ isSubmitting ? 'Memproses...' : 'Masuk' }}
            </button>
          </template>

          <template v-else>
            <div class="text-center">
              <div class="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <h3 class="text-base font-semibold text-slate-800">Verifikasi 2FA</h3>
              <p class="mt-1 text-xs text-slate-500">
                Buka aplikasi authenticator di ponsel Anda (Google Authenticator / Authy) dan masukkan 6-digit kode OTP.
              </p>
            </div>

            <div>
              <label class="mb-1.5 block text-center text-xs font-medium text-slate-700" for="otp">Kode 6-Digit OTP</label>
              <input
                id="otp"
                v-model="form.otp"
                type="text"
                maxlength="6"
                pattern="[0-9]*"
                inputmode="numeric"
                required
                autofocus
                placeholder="000000"
                class="w-full rounded-lg border border-slate-300 py-2.5 px-3 text-center font-mono text-2xl tracking-widest transition focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
            </div>

            <div class="space-y-2 pt-1">
              <button
                type="submit"
                :disabled="isSubmitting || form.otp.length < 6"
                class="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <svg v-if="isSubmitting" class="h-4 w-4 animate-spin text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"></path>
                </svg>
                {{ isSubmitting ? 'Memverifikasi...' : 'Verifikasi & Masuk' }}
              </button>
              <button
                type="button"
                class="w-full py-1 text-center text-xs text-slate-500 hover:text-slate-700"
                @click="cancel2FA"
              >
                &larr; Kembali ke form login
              </button>
            </div>
          </template>
        </form>
      </div>

      <p class="mt-6 text-center text-xs text-slate-400">
        Akses hanya untuk perangkat &amp; personel yang diotorisasi organisasi.
      </p>
    </div>

    <StatusModal
      :open="modal.open"
      :variant="modal.variant"
      :title="modal.title"
      :message="modal.message"
      :auto-close-ms="modal.variant === 'success' ? 1100 : 2200"
      @primary="modal.variant === 'success' ? goToDestination() : closeModal()"
      @close="closeModal"
    />
  </div>
</template>
