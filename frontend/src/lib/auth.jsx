import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from './api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(!!getToken())

  useEffect(() => {
    if (!getToken()) return
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setChecking(false))
  }, [])

  // Every sign-in route (login, sign-up, reset, password change) answers with { token, user }.
  const signIn = useCallback((res) => {
    setToken(res.token)
    setUser(res.user)
    return res.user
  }, [])

  const login = useCallback(async (username, password) => signIn(await api.login(username, password)), [signIn])

  // After joining: the webhook, not the browser, makes someone a member, so re-read the account.
  const refresh = useCallback(async () => {
    const u = await api.me()
    setUser(u)
    return u
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  return <AuthContext.Provider value={{ user, checking, login, signIn, logout, refresh }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
