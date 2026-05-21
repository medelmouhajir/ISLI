import { useState, useEffect } from 'react'
import { getToken, isAuthenticated, setToken, subscribe } from '@/lib/auth-store'

export function useAuth() {
  const [state, setState] = useState({
    token: getToken(),
    isAuthenticated: isAuthenticated(),
  })

  useEffect(() => {
    return subscribe(() =>
      setState({
        token: getToken(),
        isAuthenticated: isAuthenticated(),
      })
    )
  }, [])

  return {
    ...state,
    login: setToken,
    logout: () => setToken(null),
  }
}
