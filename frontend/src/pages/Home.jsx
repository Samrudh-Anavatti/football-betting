import { Link } from 'react-router-dom'
import FixtureList from '../components/FixtureList.jsx'
import TipCard from '../components/TipCard.jsx'
import { Empty, ErrorNote, Loading, SectionHead } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { api } from '../lib/api.js'
import { pct, signed } from '../lib/format.js'

function Ledger({ record }) {
  if (!record || record.tips === 0) return null
  const items = [
    ['Profit', `${signed(record.profit_units)} units`, record.profit_units >= 0 ? 'text-pitch' : 'text-red'],
    ['Return on stake', pct(record.roi), ''],
    ['Won / lost', `${record.won}–${record.lost}`, ''],
    ['Strike rate', pct(record.strike_rate, 0), ''],
    ['Average odds', record.avg_odds ?? '–', ''],
  ]
  return (
    <dl className="mt-6 grid grid-cols-2 sm:grid-cols-5 border-t border-white/15">
      {items.map(([k, v, tone]) => (
        <div key={k} className="pt-3 pr-4">
          <dt className="text-sm text-white/60">{k}</dt>
          <dd className={`num text-2xl font-semibold ${tone || 'text-white'}`}>{v}</dd>
        </div>
      ))}
    </dl>
  )
}

export default function Home() {
  const tips = useApi(() => api.tips('open'), [])
  const settled = useApi(() => api.tips('settled'), [])
  const record = useApi(() => api.record(), [])
  const upcoming = useApi(() => api.fixtures({ days: 2, limit: 40 }), [])
  const results = useApi(() => api.fixtures({ when: 'results', days: 3, limit: 30 }), [])

  return (
    <div className="space-y-10">
      <section className="-mx-4 sm:mx-0 sm:rounded-lg bg-ink text-white px-5 sm:px-8 py-8">
        <h1 className="text-4xl sm:text-5xl font-bold leading-[1.05] max-w-2xl">
          Football picks from Ivo, every one of them on the record.
        </h1>
        <p className="mt-3 max-w-xl text-white/75 text-lg">
          Each pick is posted before kick-off with the price taken and the thinking behind it, then settled against the
          final score. No deleting the losers.
        </p>
        <Ledger record={record.data} />
      </section>

      <section>
        <SectionHead title="Open picks" />
        {tips.loading ? (
          <Loading />
        ) : tips.error ? (
          <ErrorNote error={tips.error} />
        ) : tips.data.length === 0 ? (
          <Empty title="No open picks right now">New picks go up a day or two before kick-off.</Empty>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {tips.data.map((t) => (
              <TipCard key={t.id} tip={t} />
            ))}
          </div>
        )}
      </section>

      {settled.data?.length > 0 && (
        <section>
          <SectionHead title="Recently settled" />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {settled.data.slice(0, 6).map((t) => (
              <TipCard key={t.id} tip={t} />
            ))}
          </div>
        </section>
      )}

      <div className="space-y-10">
        <section>
          <SectionHead title="Coming up">
            <Link to="/fixtures" className="text-sm font-semibold underline underline-offset-4">
              All fixtures
            </Link>
          </SectionHead>
          {upcoming.loading ? (
            <Loading />
          ) : upcoming.error ? (
            <ErrorNote error={upcoming.error} />
          ) : upcoming.data.length ? (
            <FixtureList fixtures={upcoming.data} />
          ) : (
            <Empty title="Nothing in the next two days">Fixtures load once they're synced from the admin page.</Empty>
          )}
        </section>
        <section>
          <SectionHead title="Latest results">
            <Link to="/results" className="text-sm font-semibold underline underline-offset-4">
              All results
            </Link>
          </SectionHead>
          {results.loading ? (
            <Loading />
          ) : results.error ? (
            <ErrorNote error={results.error} />
          ) : results.data.length ? (
            <FixtureList fixtures={results.data} results />
          ) : (
            <Empty title="No results in the last three days" />
          )}
        </section>
      </div>
    </div>
  )
}
