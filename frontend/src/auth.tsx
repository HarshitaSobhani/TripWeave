import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, getToken, setToken } from './api'

import { AuthCtx } from './authContext'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [email, setEmail] = useState<string | null>(null)
  const [ready, setReady] = useState(() => !getToken())

  useEffect(() => {
    if (!getToken()) return
    api.me().then((u) => setEmail(u.email)).catch(() => setToken(null)).finally(() => setReady(true))
  }, [])

  const login = useCallback(async (e: string, p: string, register: boolean) => {
    const { access_token } = await (register ? api.register(e, p) : api.login(e, p))
    setToken(access_token)
    setEmail((await api.me()).email)
  }, [])
  const logout = useCallback(() => { setToken(null); setEmail(null) }, [])
  const value = useMemo(() => ({ email, ready, login, logout }), [email, ready, login, logout])
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}
