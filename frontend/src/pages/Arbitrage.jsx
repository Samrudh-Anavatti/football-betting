import JoinCard from '../components/JoinCard.jsx'
import { ArbitrageView } from '../components/admin/AiLabTab.jsx'
import { ErrorNote, Loading } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { useCan } from '../lib/access.js'
import { api } from '../lib/api.js'
import { useAuth } from '../lib/auth.jsx'

// The arbitrage list for accounts (the `arbitrage` feature). Without it: the page's shape under a blur, filled
// with a made-up example, and the way in. The real list is never sent to a visitor.

const hoursFromNow = (h) => new Date(Date.now() + h * 3600e3).toISOString()
const sampleFixture = (id, home, away, h) => ({
  id, kickoff: hoursFromNow(h), home: { name: home }, away: { name: away }, league: { name: 'Sample league', flag: '' },
})
const SAMPLE = {
  scanned_at: hoursFromNow(-0.2),
  live: [
    {
      id: 1, fixture: sampleFixture(0, 'Northfield', 'Harbour City', 20), market: 'Goals Over/Under', line: 2.5, profit: 0.021,
      best_profit: 0.024, suspect: false, first_seen: hoursFromNow(-1), prices_at: hoursFromNow(-0.3),
      legs: [
        { value: 'Over 2.5', bookmaker: 'Bookmaker A', price: 2.12, share: 0.482 },
        { value: 'Under 2.5', bookmaker: 'Bookmaker B', price: 1.97, share: 0.518 },
      ],
    },
    {
      id: 2, fixture: sampleFixture(0, 'Eastbrook', 'Riverside', 26), market: 'Both Teams Score', line: null, profit: 0.013,
      best_profit: 0.013, suspect: false, first_seen: hoursFromNow(-2), prices_at: hoursFromNow(-0.5),
      legs: [
        { value: 'Yes', bookmaker: 'Bookmaker C', price: 1.95, share: 0.519 },
        { value: 'No', bookmaker: 'Bookmaker A', price: 2.11, share: 0.481 },
      ],
    },
  ],
  recent: [],
  stats: { days: 7, closed: 14, genuine: 9, median_minutes: 55, average_profit: 0.017 },
}

function Live() {
  const { data, error, loading } = useApi(() => api.arbitrage(), [])
  if (loading && !data) return <Loading rows={4} />
  if (error) return <ErrorNote error={error} />
  return <ArbitrageView data={data} />
}

function Preview() {
  return (
    <div className="relative">
      <div aria-hidden inert="" data-nosnippet="" className="pointer-events-none select-none blur-[6px] opacity-60">
        <ArbitrageView data={SAMPLE} />
      </div>
      <div className="absolute inset-x-0 top-6 sm:top-16 flex justify-center px-2">
        <JoinCard title="The arbitrage list" className="max-w-md mx-auto">
          Every market where the best prices across five bookmakers add up to a profit whatever the result, with the
          stake to put on each side.
        </JoinCard>
      </div>
    </div>
  )
}

export default function Arbitrage() {
  const { checking } = useAuth()
  const can = useCan('arbitrage')
  return (
    <section className="space-y-6">
      <div data-tour="arbitrage">
        <h1 className="text-4xl sm:text-5xl leading-none">Arbitrage</h1>
        <p className="mt-3 max-w-prose text-[17px] text-ink-soft leading-relaxed">
          Bookmakers disagree. Now and then the best price on each outcome, taken at different bookmakers, pays out
          more than the total staked whichever way the match goes. We scan every market we price for those.
        </p>
      </div>
      {checking ? <Loading rows={4} /> : can ? <Live /> : <Preview />}
    </section>
  )
}
