import { NavLink } from 'react-router-dom'
import { useAuth } from '../lib/auth.jsx'

const NAV = [
  { to: '/', label: 'Picks', end: true },
  { to: '/fixtures', label: 'Fixtures' },
  { to: '/results', label: 'Results' },
  { to: '/history', label: 'History' },
]

export default function Shell({ children }) {
  const { user } = useAuth()
  // The current page gets an amber bar along the bottom of the header.
  const link = ({ isActive }) =>
    `relative h-full inline-flex items-center whitespace-nowrap px-2 sm:px-3 text-sm font-semibold transition-colors after:absolute after:inset-x-2 sm:after:inset-x-3 after:bottom-0 after:h-[3px] after:rounded-t-sm after:transition-colors ${
      isActive ? 'text-white after:bg-amber' : 'text-white/65 hover:text-white after:bg-transparent hover:after:bg-white/25'
    }`

  return (
    <div className="min-h-[100dvh] flex flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded focus:bg-amber focus:px-3 focus:py-2 focus:text-ink">
        Skip to content
      </a>
      <header className="bg-ink text-white">
        <div className="mx-auto max-w-6xl px-4 h-14 flex items-center gap-2 sm:gap-5">
          <NavLink to="/" className="flex items-center gap-2.5 shrink-0 group">
            <span className="h-[22px] w-4 rounded-[3px] bg-amber rotate-[10deg] shadow-[1px_2px_0_rgba(0,0,0,0.35)] transition-transform duration-300 group-hover:rotate-[-4deg]" aria-hidden />
            <span className="font-display wide text-[1.05rem] font-extrabold tracking-tight hidden sm:inline">Football Predictions AI</span>
          </NavLink>
          <nav className="flex items-stretch h-full min-w-0 overflow-x-auto" aria-label="Main">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={link}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <NavLink to="/admin" className={(s) => `ml-auto h-full ${link(s)}`}>
            {user ? 'Admin' : 'Sign in'}
          </NavLink>
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
        </div>
      </footer>
    </div>
  )
}
