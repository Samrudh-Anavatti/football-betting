import { Link } from 'react-router-dom'
import { Empty, ErrorNote, Loading, SectionHead } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { api } from '../lib/api.js'
import { useAuth } from '../lib/auth.jsx'
import SignUpWall from '../components/SignUpWall.jsx'
import { odds, pct, pickLabel, shortDate, signed } from '../lib/format.js'
import { matchPath } from '../lib/seo.js'

const RESULT = {
  won: ['W', 'bg-pitch text-white'],
  lost: ['L', 'bg-red text-white'],
  void: ['V', 'bg-ink/10 text-ink-soft'],
}

// The record is a rolling window (the API's `days`, 14): four figures and the picks settled in it, newest first,
// one line each. Older picks stay on their match pages.
export default function History() {
  const { user, checking } = useAuth()
  if (checking) return <Loading />
  if (!user)
    return (
      <SignUpWall heading="Our record" title="Every pick, won or lost">
        Our picks from the last two weeks at the price we took, with the hit rate and the profit. Free with an account.
      </SignUpWall>
    )
  return <Record />
}

function Record() {
  const tips = useApi(() => api.tips('settled', 500), [])
  const record = useApi(() => api.record(), [])
  const r = record.data
  const span = r ? `last ${r.days} days` : 'last two weeks'

  return (
    <section data-tour="history" className="space-y-6">
      <div>
        <h1 className="text-4xl sm:text-5xl leading-none">Our record</h1>
        <p className="mt-3 max-w-prose text-[17px] text-ink-soft leading-relaxed">
          Our picks from the {span}, won or lost, at the price we took. Older picks stay on their match pages. The
          bundles keep their own records: <Link to="/tonight" className="link">tonight's AI bundles</Link> and{' '}
          <Link to="/staking" className="link">our staking plan</Link>.
        </p>
      </div>
      {r && r.won + r.lost > 0 && (
        <dl aria-label={`Our picks, ${span}`} className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ['Profit, in units', signed(r.profit_units)],
            ['Won / lost', `${r.won}–${r.lost}`],
            ['Strike rate', pct(r.strike_rate, 0)],
            ['Average odds', r.avg_odds ?? '–'],
          ].map(([k, v]) => (
            <div key={k} className="panel px-4 py-3 flex flex-col-reverse">
              <dt className="text-sm text-ink-soft">{k}</dt>
              <dd className="num text-2xl sm:text-3xl font-semibold">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      <SectionHead title={`Settled in the ${span}`} count={tips.data?.length || null} />
      {tips.loading ? (
        <Loading rows={8} />
      ) : tips.error ? (
        <ErrorNote error={tips.error} />
      ) : tips.data.length === 0 ? (
        <Empty title={`No picks settled in the ${span}`}>Picks appear here once their match is over.</Empty>
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
