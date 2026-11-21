import { Link } from 'react-router-dom'
import { useJoinPath } from '../lib/access.js'
import { useAuth } from '../lib/auth.jsx'

export function LockIcon({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  )
}

// The two buttons every locked thing ends in. Someone signed in who still can't see it needs a membership
// (nothing is set that way yet: see backend/app/access.py).
export function JoinButtons({ className = '' }) {
  const { user } = useAuth()
  const join = useJoinPath()
  if (user)
    return (
      <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 ${className}`}>
        <Link to="/membership" className="btn-amber">See membership</Link>
      </div>
    )
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 ${className}`}>
      <Link to={join} className="btn-amber">Join free</Link>
      <Link to={join.replace('/signup', '/login')} className="text-sm text-ink-soft underline underline-offset-4 hover:text-ink">
        I have an account
      </Link>
    </div>
  )
}

// What a visitor sees in place of something an account unlocks: what it is, and the way in.
// `row` is the one-line version, for inside a list or a panel.
export default function JoinCard({ title, children, row = false, className = '' }) {
  const { user } = useAuth()
  if (row)
    return (
      <div data-tour="locked" className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg bg-amber-light/70 px-4 py-3 ring-1 ring-inset ring-amber/50 ${className}`}>
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-ink text-amber"><LockIcon className="h-4 w-4" /></span>
        <div className="min-w-0 flex-1 basis-56">
          <p className="font-semibold leading-snug">{title}</p>
          {children && <p className="text-sm text-ink-soft">{children}</p>}
        </div>
        <JoinButtons />
      </div>
    )
  return (
    <div data-tour="locked" className={`panel shadow-lift p-6 text-center ${className}`}>
      <span className="inline-grid h-11 w-11 place-items-center rounded-full bg-ink text-amber"><LockIcon /></span>
      <p className="mt-3 text-sm font-semibold uppercase tracking-wider text-amber-dark">{user ? 'For members' : 'Free with an account'}</p>
      <h2 className="mt-1 text-2xl">{title}</h2>
      {children && <p className="mt-2 text-ink-soft max-w-prose mx-auto">{children}</p>}
      <JoinButtons className="mt-4 justify-center" />
    </div>
  )
}
