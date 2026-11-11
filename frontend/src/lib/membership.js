import { useEffect, useState } from 'react'
import { api } from './api.js'

// Whether membership is open and its price: asked once per visit, shared by the header, footer and pages.
let pending = null

export function useMembershipInfo() {
  const [info, setInfo] = useState(null)
  useEffect(() => {
    let alive = true
    pending ??= api.membership().catch(() => {
      pending = null // try again on the next page
      return { open: false, price: null }
    })
    pending.then((v) => alive && setInfo(v))
    return () => {
      alive = false
    }
  }, [])
  return info
}

export const fullDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '–'
