import { create } from 'zustand'
import { fetchMe, logout as apiLogout } from '../api/client'
import type { User } from '../api/types'

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

interface AuthState {
  user: User | null
  status: AuthStatus
  checkAuth: () => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  status: 'loading',

  checkAuth: async () => {
    try {
      const user = await fetchMe()
      set({ user, status: 'authenticated' })
    } catch {
      set({ user: null, status: 'unauthenticated' })
    }
  },

  logout: async () => {
    await apiLogout()
    set({ user: null, status: 'unauthenticated' })
  },
}))
