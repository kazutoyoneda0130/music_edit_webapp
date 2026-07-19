import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { useAuthStore } from '../store/authStore'
import { LoginPage } from './LoginPage'

interface AuthGateProps {
  children: ReactNode
}

export function AuthGate({ children }: AuthGateProps) {
  const status = useAuthStore((s) => s.status)
  const checkAuth = useAuthStore((s) => s.checkAuth)

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  if (status === 'loading') {
    return <div className="auth-loading">読み込み中…</div>
  }

  if (status === 'unauthenticated') {
    return <LoginPage />
  }

  return <>{children}</>
}
