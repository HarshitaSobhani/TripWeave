import { createContext, useContext } from 'react'

export interface AuthState {
  email: string | null
  ready: boolean
  login: (email: string, password: string, register: boolean) => Promise<void>
  logout: () => void
}

export const AuthCtx = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const v = useContext(AuthCtx)
  if (!v) throw new Error('AuthProvider missing')
  return v
}
