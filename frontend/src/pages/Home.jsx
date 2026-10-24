import { Link } from 'react-router-dom'
import FeaturedMatch from '../components/FeaturedMatch.jsx'
import FixtureList from '../components/FixtureList.jsx'
import TipCard from '../components/TipCard.jsx'
import { Empty, ErrorNote, Loading, SectionHead } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { api } from '../lib/api.js'
import { pct } from '../lib/format.js'

// The record in money rather than units: a unit is £10, Ivo's standard stake.
const UNIT = 10
const pounds = (v, dp = 0) => `£${Math.abs(v).toLocaleString('en-GB', { minimumFractionDigits: dp, maximumFractionDigits: dp })}`

// Faint pitch markings behind the banner: halfway line, centre circle and spot.
function PitchLines() {
  return (
    <svg aria-hidden className="pointer-events-none absolute inset-0 h-full w-full" preserveAspectRatio="xMidYMid slice" viewBox="0 0 1200 520">
      <g fill="none" stroke="white" strokeOpacity="0.07" strokeWidth="2">
        <line x1="860" y1="0" x2="860" y2="520" />
        <circle cx="860" cy="260" r="150" />
        <circle cx="860" cy="260" r="4" fill="white" fillOpacity="0.12" />
        <rect x="1080" y="110" width="160" height="300" />
        <path d="M1080 200 a 70 70 0 0 0 0 120" />
      </g>
    </svg>
  )
}

// The record, as the banner's headline figure plus a row of supporting numbers.
function Ledger({ record }) {
  if (!record || record.tips === 0) return null
  const profit = record.profit_units * UNIT
  const items = [
    [`Every £${UNIT} staked returned`, record.roi == null ? '–' : pounds(UNIT * (1 + record.roi), 2)],
    ['Won / lost', `${record.won}–${record.lost}`],
    ['Strike rate', pct(record.strike_rate, 0)],
    ['Average odds', record.avg_odds ?? '–'],
  ]
  return (
    <div className="mt-8">
      <p className={`num wide font-black leading-[0.85] tracking-[-0.04em] text-[clamp(2.75rem,8vw,4.75rem)] ${profit >= 0 ? 'text-pitch-bright' : 'text-red'}`}>
        {profit < 0 ? '−' : '+'}
        {pounds(profit)}
      </p>
      <p className="mt-2 text-sm text-white/60">Profit so far at £{UNIT} a unit. It moves with every result.</p>
      <dl className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-y-4 border-t border-white/15 pt-4">
        {items.map(([k, v], i) => (
          <div key={k} className={`pr-4 flex flex-col-reverse justify-end gap-0.5 ${i % 2 ? 'pl-4 border-l border-white/15' : ''} ${i === 2 ? 'sm:pl-4 sm:border-l border-white/15' : ''}`}>
            <dt className="text-xs text-white/55">{k}</dt>
            <dd className="num wide text-2xl font-bold text-white">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

export default function Home() {
  const tips = useApi(() => api.tips('open'), [])
  const settled = useApi(() => api.tips('settled'), [])
  const record = useApi(() => api.record(), [])
  const featured = useApi(() => api.featured(), [])
  const upcoming = useApi(() => api.fixtures({ days: 2, limit: 40, tier: 'main' }), [])
  const results = useApi(() => api.fixtures({ when: 'results', days: 3, limit: 30, tier: 'main' }), [])

  return (
    <div className="space-y-14">
      <section className="relative isolate overflow-hidden -mx-4 -mt-6 sm:mx-0 sm:mt-0 sm:rounded-2xl bg-ink text-white px-5 sm:px-10 pt-9 pb-8 sm:py-11">
        <PitchLines />
        <div className={`grid grid-cols-1 gap-10 ${featured.data?.ai ? 'lg:grid-cols-[minmax(0,1fr)_23rem] lg:items-center lg:gap-14' : ''}`}>
          <div className="min-w-0">
            <h1 className="text-[2.1rem] sm:text-5xl font-extrabold leading-[1.02] max-w-2xl">
              Expert football picks from Ivo, every one of them on the record.
            </h1>
            <p className="mt-4 max-w-xl text-white/70 text-[17px] leading-relaxed">
              Single bets, no long-odds accumulators. Each pick goes up before kick-off with the price taken and the
              thinking behind it, then settles against the final score. The losers stay up too.
            </p>
            <Ledger record={record.data} />
          </div>
          <FeaturedMatch data={featured.data} />
        </div>
      </section>

      <section>
        <SectionHead title="Open picks" count={tips.data?.length || null} />
        {tips.loading ? (
          <Loading />
        ) : tips.error ? (
          <ErrorNote error={tips.error} />
        ) : tips.data.length === 0 ? (
          <Empty title="No open picks right now">New picks go up a day or two before kick-off.</Empty>
        ) : (
          <div className="grid gap-x-5 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
            {tips.data.map((t) => (
              <TipCard key={t.id} tip={t} />
            ))}
          </div>
        )}
      </section>

      {settled.data?.length > 0 && (
        <section>
          <SectionHead title="Recently settled">
            <Link to="/history" className="link">
              All past picks
            </Link>
          </SectionHead>
          <div className="grid gap-x-5 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
            {settled.data.slice(0, 6).map((t) => (
              <TipCard key={t.id} tip={t} />
            ))}
          </div>
        </section>
      )}

      <div className="space-y-14">
        <section>
          <SectionHead title="Coming up">
            <Link to="/fixtures" className="link">
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
            <Link to="/results" className="link">
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
