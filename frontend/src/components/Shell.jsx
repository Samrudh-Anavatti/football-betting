import { Link, NavLink, useLocation } from 'react-router-dom'
import { useJoinPath } from '../lib/access.js'
import { openCookieSettings } from '../lib/analytics.js'
import { useAuth } from '../lib/auth.jsx'
import { useMembershipInfo } from '../lib/membership.js'
import { WHATSAPP_URL } from '../lib/support.js'

// The sections, by what a visitor is after rather than by what we store: today's page, the matches, the bundles,
// the arbitrage list and our record. `also` lists the other addresses a section owns, so it stays lit on them.
const NAV = [
  { to: '/', label: 'Today', end: true },
  { to: '/fixtures', label: 'Matches', also: ['/results', '/match'] },
  { to: '/tonight', label: 'Bundles', also: ['/staking'], tour: 'nav-bundles' },
  { to: '/arbitrage', label: 'Arbitrage', short: 'Arbs', tour: 'nav-arbitrage' }, // `short`: on phones
  { to: '/history', label: 'Record' },
]

// A strip of tabs under a page's heading, for sections that hold more than one page (Matches, Bundles).
export function SubNav({ tabs }) {
  return (
    <nav className="segmented" aria-label="In this section">
      {tabs.map(([to, label]) => (
        <NavLink key={to} to={to} end className={({ isActive }) => `segment px-4 ${isActive ? 'segment-on' : ''}`}>
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

export default function Shell({ children }) {
  const { user } = useAuth()
  const membership = useMembershipInfo()
  const { pathname } = useLocation()
  const join = useJoinPath()
  const me = !user ? null : user.is_admin ? { to: '/admin', label: 'Admin' } : { to: '/account', label: 'Account' }
  const onAuthPage = ['/signup', '/login', '/forgot', '/reset'].includes(pathname)
  // The current section gets an amber bar along the bottom of the header.
  const cls = (on) =>
    `relative h-full inline-flex items-center whitespace-nowrap px-[5px] sm:px-3 text-[13px] sm:text-sm font-semibold transition-colors after:absolute after:inset-x-[5px] sm:after:inset-x-3 after:bottom-0 after:h-[3px] after:rounded-t-sm after:transition-colors ${
      on ? 'text-white after:bg-amber' : 'text-white/65 hover:text-white after:bg-transparent hover:after:bg-white/25'
    }`

  return (
    <div className="min-h-[100dvh] flex flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded focus:bg-amber focus:px-3 focus:py-2 focus:text-ink">
        Skip to content
      </a>
      <header className="bg-ink text-white">
        <div className="mx-auto max-w-6xl px-4 h-14 flex items-center gap-1.5 sm:gap-5">
          <NavLink to="/" className="flex items-center gap-2.5 shrink-0 group">
            <span className="h-[22px] w-4 rounded-[3px] bg-amber rotate-[10deg] shadow-[1px_2px_0_rgba(0,0,0,0.35)] transition-transform duration-300 group-hover:rotate-[-4deg]" aria-hidden />
            <span className="font-display wide text-[1.05rem] font-extrabold tracking-tight hidden lg:inline">Football Predictions AI</span>
          </NavLink>
          <nav className="flex items-stretch h-full min-w-0 overflow-x-auto" aria-label="Main">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                data-tour={n.tour}
                className={({ isActive }) => cls(isActive || n.also?.some((p) => pathname === p || pathname.startsWith(`${p}/`)))}
              >
                {n.short ? (
                  <>
                    <span className="sm:hidden">{n.short}</span>
                    <span className="hidden sm:inline">{n.label}</span>
                  </>
                ) : (
                  n.label
                )}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex h-full shrink-0 items-center gap-1 sm:gap-2">
            {me ? (
              <NavLink to={me.to} className={({ isActive }) => cls(isActive)} aria-label={me.label} data-tour="nav-account">
                {/* An icon on phones, where the sections need the room. */}
                <svg viewBox="0 0 24 24" className="h-5 w-5 sm:hidden" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
                  <circle cx="12" cy="8" r="4" />
                  <path d="M4 21a8 8 0 0 1 16 0" />
                </svg>
                <span className="hidden sm:inline">{me.label}</span>
              </NavLink>
            ) : (
              <>
                <NavLink to={onAuthPage ? '/login' : join.replace('/signup', '/login')} className={({ isActive }) => `hidden sm:inline-flex ${cls(isActive)}`}>
                  Sign in
                </NavLink>
                <Link to={onAuthPage ? '/signup' : join} data-tour="nav-join" className="btn-amber px-2.5 py-1.5 text-[13px] sm:px-3.5 sm:text-sm">
                  Join<span className="hidden sm:inline">&nbsp;free</span>
                </Link>
              </>
            )}
          </div>
        </div>
      </header>
      <main id="main" className="flex-1 mx-auto w-full min-w-0 max-w-6xl px-4 pt-6 pb-16">
        {children}
      </main>
      <footer className="bg-ink text-white/60">
        <div className="mx-auto max-w-6xl px-4 py-6 text-sm flex flex-wrap items-center gap-x-6 gap-y-2">
          <span className="inline-flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-full border-2 border-white/70 font-display text-xs font-bold text-white">18+</span>
            Bet with money you can afford to lose. Free support at BeGambleAware.org.
          </span>
          <span className="sm:ml-auto">Fixtures, research and prices by API-Football</span>
          <span className="flex flex-wrap gap-x-4 gap-y-2">
            <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer" className="hover:text-white underline underline-offset-4">Help on WhatsApp</a>
            <Link to="/friends" className="hover:text-white underline underline-offset-4">Football Friends</Link>
            {membership?.open && (
              <>
                <Link to="/membership" className="hover:text-white underline underline-offset-4">Membership</Link>
                <Link to="/terms" className="hover:text-white underline underline-offset-4">Terms</Link>
              </>
            )}
            <Link to="/privacy" className="hover:text-white underline underline-offset-4">Privacy</Link>
            <button type="button" className="hover:text-white underline underline-offset-4" onClick={openCookieSettings}>
              Cookie settings
            </button>
          </span>
        </div>
      </footer>
    </div>
  )
}
