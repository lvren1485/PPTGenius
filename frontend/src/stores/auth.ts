import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userId = ref(Number(localStorage.getItem('userId')) || 0)
  const userName = ref(localStorage.getItem('userName') || '')

  const isLoggedIn = computed(() => !!token.value)

  function setAuth(t: string, uid: number, name: string) {
    token.value = t
    userId.value = uid
    userName.value = name
    localStorage.setItem('token', t)
    localStorage.setItem('userId', String(uid))
    localStorage.setItem('userName', name)
  }

  function logout() {
    token.value = ''
    userId.value = 0
    userName.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('userId')
    localStorage.removeItem('userName')
  }

  return { token, userId, userName, isLoggedIn, setAuth, logout }
})
