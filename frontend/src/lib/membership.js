import { useEffect, useState } from 'react'
import { api } from './api.js'
import { useAuth } from './auth.jsx'

// Whether membership is open and its price: asked once per visit for whoever is signed in (while we test on the
// payment provider's sandbox it is open to test accounts only), shared by the header, footer and pages.
const pending = {}

export function useMembershipInfo() {
  const { user } = useAuth()
  const who = user?.id ?? 0
  const [info, setInfo] = useState(null)
  useEffect(() => {
    let alive = true
    pending[who] ??= api.membership().catch(() => {
      delete pending[who] // try again on the next page
      return { open: false, price: null }
    })
    pending[who].then((v) => alive && setInfo(v))
    return () => {
      alive = false
    }
  }, [who])
  return info
}

export const fullDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '–'
