import { useState } from 'react'
import { Link } from 'react-router-dom'
import DailyBundle from '../components/DailyBundle.jsx'
import FeaturedMatch from '../components/FeaturedMatch.jsx'
import FixtureList from '../components/FixtureList.jsx'
import { JoinButtons, LockIcon } from '../components/JoinCard.jsx'
import TipCard from '../components/TipCard.jsx'
import { Empty, ErrorNote, LeagueBadge, Loading, SectionHead } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { useCan, useJoinPath } from '../lib/access.js'
import { api } from '../lib/api.js'
import { useAuth } from '../lib/auth.jsx'
import { dayLabel, kickoffTime, pct } from '../lib/format.js'
import { matchPath } from '../lib/seo.js'

// The front page, in the order a newcomer needs it: what this is and the way in, proof (the record), what's on
// tonight (the bundles, with the staking plan and arbitrage beside them), today's picks, then the matches.

// The record in money rather than units: a unit is £1.
const UNIT = 1
// The return-on-stake stat reads better on a typical £10 bet.
const EXAMPLE_STAKE = 10
const pounds = (v, dp = 0) => `£${Math.abs(v).toLocaleString('en-GB', { minimumFractionDigits: dp, maximumFractionDigits: dp })}`
const PICKS_SHOWN = 6 // open picks before "show all"

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

// The record over its rolling window (the API's `days`): the headline figure plus a row of supporting numbers,
// linking to the picks behind it.
function Ledger({ record }) {
  if (!record || record.won + record.lost === 0) return null
  const profit = record.profit_units * UNIT
  const items = [
    [`Every £${EXAMPLE_STAKE} staked returned`, record.roi == null ? '–' : pounds(EXAMPLE_STAKE * (1 + record.roi), 2)],
    ['Won / lost', `${record.won}–${record.lost}`],
    ['Strike rate', pct(record.strike_rate, 0)],
    ['Average odds', record.avg_odds ?? '–'],
  ]
  return (
    <div data-tour="record" className="mt-8">
      <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
        <p className={`num wide font-black leading-[0.85] tracking-[-0.04em] text-[clamp(2.4rem,7vw,4rem)] ${profit >= 0 ? 'text-pitch-bright' : 'text-red'}`}>
          {profit < 0 ? '−' : '+'}
          {pounds(profit, 2)}
        </p>
        <p className="text-sm text-white/60 pb-0.5">
          our picks over the last {record.days} days, at £{UNIT} a unit.{' '}
          <Link to="/history" className="underline underline-offset-4 hover:text-white">See each one</Link>
        </p>
      </div>
      <dl className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-y-4 border-t border-white/15 pt-4">
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

// Tonight's bundles, as the next session on offer: its matches and the way to the slips.
function TonightCard({ sessions, record }) {
  const can = useCan('tonight')
  const s = sessions?.sessions?.[0]
  const r = record
  return (
    <div className="panel overflow-hidden flex flex-col">
      <div className="bg-ink text-white px-5 py-4">
        <p className="text-xs font-bold uppercase tracking-wider text-amber">Tonight's bundles</p>
        <h3 className="mt-1 text-2xl sm:text-[1.7rem] leading-tight">
          {s ? `${dayLabel(s.at)}, ${kickoffTime(s.at)}: ${s.matches.length} matches to bundle` : 'Bundles for the matches you watch'}
        </h3>
        <p className="mt-1.5 text-sm text-white/70 max-w-prose">
          Tick what you're watching and the AI turns its surest calls into up to three bets, at about 3.00, 6.00 or
          10.00. Every bundle shown goes on the record.
        </p>
      </div>
      {s ? (
        <ul className="divide-y divide-ink/5">
          {s.matches.slice(0, 4).map((m) => (
            <li key={m.id}>
              <Link to={matchPath(m)} className="flex items-center gap-3 px-5 py-2 text-[15px] hover:bg-amber-light/50">
                <LeagueBadge league={m.league} />
                <span className="min-w-0 flex-1 truncate">{m.home.name} v {m.away.name}</span>
                <span className="num text-sm text-ink-soft shrink-0">{kickoffTime(m.kickoff)}</span>
              </Link>
            </li>
          ))}
          {s.matches.length > 4 && <li className="px-5 py-2 text-sm text-ink-soft">and {s.matches.length - 4} more</li>}
        </ul>
      ) : !sessions ? (
        <div className="px-5 py-3"><Loading rows={2} /></div>
      ) : (
        <p className="px-5 py-4 text-ink-soft">
          No session in the next three days yet. They appear once a couple of matches kick off around the same time.
        </p>
      )}
      <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-ink/10 px-5 py-3.5">
        <Link to="/tonight" className="btn-primary">
          {!can && <LockIcon className="h-4 w-4" />}
          {can ? 'Build my bundles' : "See tonight's session"}
        </Link>
        {r?.bundles > 0 && (
          <span className="text-sm text-ink-soft">
            <span className="num font-semibold text-ink">{r.won}</span> of <span className="num">{r.bundles}</span> bundles landed in the last {r.days} days
          </span>
        )}
      </div>
    </div>
  )
}

// A smaller door to one of the other account features.
function ToolCard({ to, kicker, title, children, feature }) {
  const can = useCan(feature)
  return (
    <Link to={to} className="panel group flex flex-col p-5 transition hover:shadow-lift hover:-translate-y-0.5">
      <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-amber-dark">
        {kicker}
        {!can && <LockIcon className="h-3.5 w-3.5" />}
      </p>
      <h3 className="mt-1 text-xl leading-tight">{title}</h3>
      <p className="mt-1.5 text-sm text-ink-soft">{children}</p>
      <span className="mt-auto pt-3 text-sm font-semibold underline decoration-amber decoration-2 underline-offset-4 group-hover:decoration-ink">
        {can ? 'Open' : 'Take a look'}
      </span>
    </Link>
  )
}

// The open picks a visitor can't see yet: which matches they're on, and the way in.
function LockedPicks({ locked }) {
  if (!locked?.length) return null
  const names = locked.slice(0, 3).map((x) => `${x.fixture.home.name} v ${x.fixture.away.name}`)
  return (
    <div data-tour="locked" className="rounded-xl border-2 border-dashed border-ink/20 bg-paper/60 p-5 flex flex-col">
      <span className="grid h-9 w-9 place-items-center rounded-full bg-ink text-amber"><LockIcon className="h-4 w-4" /></span>
      <h3 className="mt-3 text-xl leading-tight">
        {locked.length} more pick{locked.length === 1 ? '' : 's'} open today
      </h3>
      <p className="mt-1.5 text-sm text-ink-soft">
        On {names.join(', ')}
        {locked.length > names.length ? ` and ${locked.length - names.length} more` : ''}. Free with an account.
      </p>
      <JoinButtons className="mt-auto pt-4" />
    </div>
  )
}

export default function Home() {
  const { user } = useAuth()
  const join = useJoinPath()
  const who = user?.id
  const tips = useApi(() => api.tips('open'), [who])
  const locked = useApi(() => api.lockedTips(), [who])
  const settled = useApi(() => api.tips('settled', 3), [])
  const record = useApi(() => api.record(), [])
  const featured = useApi(() => api.featured(), [who])
  const sessions = useApi(() => api.tonightSessions(), [])
  const bundleRecord = useApi(() => api.tonightRecord(), [])
  const upcoming = useApi(() => api.fixtures({ days: 1, limit: 14, tier: 'main' }), [])
  const [allPicks, setAllPicks] = useState(false)

  // Most confident first, so the first few shown are the ones we rate.
  const open = [...(tips.data || [])].sort((a, b) => (b.confidence || 0) - (a.confidence || 0) || new Date(a.fixture.kickoff) - new Date(b.fixture.kickoff))
  const shown = allPicks ? open : open.slice(0, PICKS_SHOWN)

  return (
    <div className="space-y-14">
      <section className="relative isolate overflow-hidden -mx-4 -mt-6 sm:mx-0 sm:mt-0 sm:rounded-2xl bg-ink text-white px-5 sm:px-10 pt-8 pb-8 sm:py-11">
        <PitchLines />
        <div className={`grid grid-cols-1 gap-10 ${featured.data?.ai ? 'lg:grid-cols-[minmax(0,1fr)_23rem] lg:items-center lg:gap-14' : ''}`}>
          <div className="min-w-0">
            <h1 className="text-[2.1rem] sm:text-5xl font-extrabold leading-[1.02] max-w-2xl">
              Football picks and bundles for tonight's matches, all on the record.
            </h1>
            <p className="mt-4 max-w-xl text-white/70 text-[17px] leading-relaxed">
              Our team's picks, bundles built by AI for the games you're watching, and the odds, form and analysis for
              every match. Every result stays up, the losers too.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-3">
              {user ? (
                <Link to="/tonight" className="btn-amber px-5 py-2.5 text-base">Tonight's bundles</Link>
              ) : (
                <Link to={join} className="btn-amber px-5 py-2.5 text-base">Join free</Link>
              )}
              <Link to={user ? '/fixtures' : '/tonight'} className="text-[15px] font-semibold text-white underline decoration-amber decoration-2 underline-offset-4 hover:decoration-white">
                {user ? 'All matches' : "See tonight's bundles"}
              </Link>
              {!user && <span className="basis-full text-sm text-white/55">An email and a password. No card.</span>}
            </div>
            <Ledger record={record.data} />
          </div>
          <FeaturedMatch data={featured.data} />
        </div>
      </section>

      <section data-tour="daily">
        <SectionHead title="Bundle of the day" />
        <DailyBundle />
      </section>

      <section data-tour="tonight">
        <SectionHead title="Tonight" />
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <TonightCard sessions={sessions.data} record={bundleRecord.data} />
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-1">
            <ToolCard to="/staking" kicker="Staking plan" title="Our picks, bundled at about 6.00" feature="staking">
              One bet at a time, with each stake worked out and scaled to yours.
            </ToolCard>
            <ToolCard to="/arbitrage" kicker="Arbitrage" title="Prices that add up to a profit" feature="arbitrage">
              Markets where five bookmakers disagree enough to cover every outcome.
            </ToolCard>
          </div>
        </div>
      </section>

      <section data-tour="picks">
        <SectionHead title="Today's picks" count={open.length + (locked.data?.length || 0) || null}>
          <Link to="/history" className="link">Our record</Link>
        </SectionHead>
        {tips.loading && !tips.data ? (
          <Loading />
        ) : tips.error ? (
          <ErrorNote error={tips.error} />
        ) : open.length === 0 && !locked.data?.length ? (
          <Empty title="No open picks right now">New picks go up a day or two before kick-off.</Empty>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-x-5 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
              {shown.map((t) => (
                <TipCard key={t.id} tip={t} />
              ))}
              <LockedPicks locked={locked.data} />
            </div>
            {open.length > PICKS_SHOWN && (
              <button type="button" className="btn-ghost mt-6" onClick={() => setAllPicks(!allPicks)}>
                {allPicks ? 'Show fewer' : `Show all ${open.length} picks`}
              </button>
            )}
          </>
        )}
      </section>

      {settled.data?.length > 0 && (
        <section>
          <SectionHead title="Latest results on our picks">
            <Link to="/history" className="link">All past picks</Link>
          </SectionHead>
          <div className="grid grid-cols-1 gap-x-5 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
            {settled.data.map((t) => (
              <TipCard key={t.id} tip={t} />
            ))}
          </div>
        </section>
      )}

      <section>
        <SectionHead title="Next up">
          <Link to="/fixtures" className="link">All fixtures</Link>
          <Link to="/results" className="link">Results</Link>
        </SectionHead>
        {upcoming.loading && !upcoming.data ? (
          <Loading />
        ) : upcoming.error ? (
          <ErrorNote error={upcoming.error} />
        ) : upcoming.data.length ? (
          <FixtureList fixtures={upcoming.data} />
        ) : (
          <Empty title="Nothing in the next day">
            <Link to="/fixtures" className="link">See the week's fixtures</Link>
          </Empty>
        )}
      </section>
    </div>
  )
}
