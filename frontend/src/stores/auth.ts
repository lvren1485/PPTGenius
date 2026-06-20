import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const STORAGE_KEY_TOKEN = 'token'
const STORAGE_KEY_USER_ID = 'userId'
const STORAGE_KEY_USER_NAME = 'userName'
const STORAGE_KEY_EXPIRY = 'token_expiry'
const REMEMBER_DAYS = 7

function getStorage(): Storage {
  const remember = localStorage.getItem('remember_me') === '1'
  return remember ? localStorage : sessionStorage
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref('')
  const userId = ref(0)
  const userName = ref('')

  const isLoggedIn = computed(() => !!token.value)

  function tryAutoLogin(): boolean {
    // Try localStorage first (remembered), then sessionStorage
    for (const storage of [localStorage, sessionStorage]) {
      const t = storage.getItem(STORAGE_KEY_TOKEN)
      const uid = storage.getItem(STORAGE_KEY_USER_ID)
      const name = storage.getItem(STORAGE_KEY_USER_NAME)
      const expiry = storage.getItem(STORAGE_KEY_EXPIRY)

      if (t && uid) {
        if (expiry) {
          const expiresAt = Number(expiry)
          if (Date.now() > expiresAt) {
            // Expired — clear and skip
            storage.removeItem(STORAGE_KEY_TOKEN)
            storage.removeItem(STORAGE_KEY_USER_ID)
            storage.removeItem(STORAGE_KEY_USER_NAME)
            storage.removeItem(STORAGE_KEY_EXPIRY)
            continue
          }
        }
        token.value = t
        userId.value = Number(uid)
        userName.value = name || ''
        // Copy to current storage
        const currentStorage = getStorage()
        if (currentStorage !== storage) {
          currentStorage.setItem(STORAGE_KEY_TOKEN, t)
          currentStorage.setItem(STORAGE_KEY_USER_ID, uid)
          currentStorage.setItem(STORAGE_KEY_USER_NAME, name || '')
          if (expiry) currentStorage.setItem(STORAGE_KEY_EXPIRY, expiry)
        }
        return true
      }
    }
    return false
  }

  function setAuth(t: string, uid: number, name: string, remember: boolean = false) {
    token.value = t
    userId.value = uid
    userName.value = name

    const storage: Storage = remember ? localStorage : sessionStorage
    storage.setItem(STORAGE_KEY_TOKEN, t)
    storage.setItem(STORAGE_KEY_USER_ID, String(uid))
    storage.setItem(STORAGE_KEY_USER_NAME, name)

    if (remember) {
      localStorage.setItem('remember_me', '1')
      const expiry = Date.now() + REMEMBER_DAYS * 86400 * 1000
      storage.setItem(STORAGE_KEY_EXPIRY, String(expiry))
    } else {
      localStorage.removeItem('remember_me')
      localStorage.removeItem(STORAGE_KEY_EXPIRY)
      sessionStorage.removeItem(STORAGE_KEY_EXPIRY)
    }
  }

  function logout() {
    token.value = ''
    userId.value = 0
    userName.value = ''
    for (const storage of [localStorage, sessionStorage]) {
      storage.removeItem(STORAGE_KEY_TOKEN)
      storage.removeItem(STORAGE_KEY_USER_ID)
      storage.removeItem(STORAGE_KEY_USER_NAME)
      storage.removeItem(STORAGE_KEY_EXPIRY)
    }
    localStorage.removeItem('remember_me')
  }

  // Initialize from storage on store creation
  tryAutoLogin()

  return { token, userId, userName, isLoggedIn, setAuth, logout, tryAutoLogin }
})
