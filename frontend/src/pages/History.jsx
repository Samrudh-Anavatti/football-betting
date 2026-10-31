import { Link } from 'react-router-dom'
import { Empty, ErrorNote, Loading, SectionHead } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { api } from '../lib/api.js'
import { odds, pickLabel, shortDate, signed } from '../lib/format.js'
import { matchPath } from '../lib/seo.js'

const RESULT = {
  won: ['W', 'bg-pitch text-white'],
  lost: ['L', 'bg-red text-white'],
  void: ['V', 'bg-ink/10 text-ink-soft'],
}

// Every settled pick, newest first: one line each, no reasoning or detail.
export default function History() {
  const tips = useApi(() => api.tips('settled', 1000), [])

  return (
    <section>
      <SectionHead title="Past picks" count={tips.data?.length || null} />
      {tips.loading ? (
        <Loading rows={8} />
      ) : tips.error ? (
        <ErrorNote error={tips.error} />
      ) : tips.data.length === 0 ? (
        <Empty title="No settled picks yet">Picks appear here once their match is over.</Empty>
      ) : (
        <ol className="panel divide-y divide-ink/5">
          {tips.data.map((t) => {
            const fx = t.fixture
            const [letter, tone] = RESULT[t.status] || ['?', 'bg-ink/10']
            return (
              <li key={t.id} className="flex items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2.5 text-sm">
                <span className="hidden sm:block w-16 shrink-0 text-ink-soft num">{shortDate(fx.kickoff)}</span>
                <div className="min-w-0 flex-1">
                  <Link to={matchPath(fx)} className="block truncate font-semibold hover:underline underline-offset-4">
                    {pickLabel(t, fx)}
                  </Link>
                  <span className="block truncate text-ink-soft">
                    <span className="sm:hidden num">{shortDate(fx.kickoff)} · </span>
                    {fx.home.name} {fx.home_goals ?? ''}–{fx.away_goals ?? ''} {fx.away.name}
                  </span>
                </div>
                <span className="w-10 shrink-0 text-right num">{odds(t.odds)}</span>
                <span className={`h-6 w-6 shrink-0 grid place-items-center rounded text-xs font-bold ${tone}`} aria-label={t.status}>
                  {letter}
                </span>
                <span className={`w-[3.75rem] shrink-0 text-right num font-semibold ${t.profit_units > 0 ? 'text-pitch' : t.profit_units < 0 ? 'text-red' : 'text-ink-soft'}`}>
                  {signed(t.profit_units)}u
                </span>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
