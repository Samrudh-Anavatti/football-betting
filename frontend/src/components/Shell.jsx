import { NavLink } from 'react-router-dom'
import { useAuth } from '../lib/auth.jsx'

const NAV = [
  { to: '/', label: 'Picks', end: true },
  { to: '/fixtures', label: 'Fixtures' },
  { to: '/results', label: 'Results' },
]

export default function Shell({ children }) {
  const { user } = useAuth()
  const link = ({ isActive }) =>
    `px-3 py-1.5 rounded-md text-sm font-semibold transition ${isActive ? 'bg-white/10 text-white' : 'text-white/70 hover:text-white'}`

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-ink text-white">
        <div className="mx-auto max-w-6xl px-4 h-14 flex items-center gap-2 sm:gap-4">
          <NavLink to="/" className="flex items-center gap-2 sm:mr-2 shrink-0">
            <span className="h-6 w-[18px] rounded-[3px] bg-amber rotate-[8deg]" aria-hidden />
            <span className="font-display text-xl font-bold hidden sm:inline">Ivo's Picks</span>
          </NavLink>
          <nav className="flex items-center gap-1 min-w-0 overflow-x-auto">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={link}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <NavLink to="/admin" className={(s) => `ml-auto ${link(s)}`}>
            {user ? 'Admin' : 'Sign in'}
          </NavLink>
        </div>
      </header>
      <main className="flex-1 mx-auto w-full min-w-0 max-w-6xl px-4 py-6">{children}</main>
      <footer className="border-t border-ink/10">
        <div className="mx-auto max-w-6xl px-4 py-5 text-sm text-ink-soft flex flex-wrap gap-x-6 gap-y-1">
          <span>18+ only. Bet with money you can afford to lose. Free support at BeGambleAware.org.</span>
          <span className="sm:ml-auto">Fixtures, research and prices by API-Football</span>
        </div>
      </footer>
    </div>
  )
}
