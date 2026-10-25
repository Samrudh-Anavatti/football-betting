import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { OPEN_SETTINGS, setConsent, startAnalytics, storedConsent, trackPage } from '../lib/analytics.js'

// Asks once whether Google Analytics may set cookies (Accept and Reject equally easy to pick),
// reopens from the footer's "Cookie settings", and reports each page view.
export default function ConsentBanner() {
  const [open, setOpen] = useState(() => storedConsent() == null)
  const { pathname } = useLocation()

  useEffect(() => {
    startAnalytics()
    const show = () => setOpen(true)
    window.addEventListener(OPEN_SETTINGS, show)
    return () => window.removeEventListener(OPEN_SETTINGS, show)
  }, [])

  useEffect(() => {
    if (!pathname.startsWith('/admin')) trackPage(pathname)
  }, [pathname])

  if (!open) return null
  const choose = (value) => {
    setConsent(value)
    setOpen(false)
  }
  return (
    <div role="dialog" aria-label="Cookie settings" className="fixed inset-x-0 bottom-0 z-40 p-3 sm:p-4">
      <div className="mx-auto max-w-3xl rounded-xl bg-ink text-white shadow-lift px-4 py-4 sm:px-5 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-5">
        <p className="text-sm leading-relaxed text-white/85 flex-1">
          Can we use Google Analytics cookies to see which pages people use? No ads, and you can change your mind any
          time under Cookie settings.{' '}
          <Link to="/privacy" className="underline underline-offset-4 text-white">
            Privacy
          </Link>
        </p>
        <div className="flex gap-2 shrink-0">
          <button type="button" className="btn bg-white/10 text-white hover:bg-white/20 flex-1 sm:flex-none" onClick={() => choose('denied')}>
            Reject
          </button>
          <button type="button" className="btn bg-amber text-ink hover:brightness-105 flex-1 sm:flex-none" onClick={() => choose('granted')}>
            Accept
          </button>
        </div>
      </div>
    </div>
  )
}
