import { useEffect, useState } from 'react'
import BookLink from './BookLink.jsx'
import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi.js'
import { useCan } from '../lib/access.js'
import { api } from '../lib/api.js'
import { dayLabel, kickoffTime, money, pickLabel } from '../lib/format.js'
import { matchPath } from '../lib/seo.js'
import JoinCard from './JoinCard.jsx'
import { LeagueBadge, Loading, Price } from './ui.jsx'

// The bundle of the day: the one bet the AI stands behind today, open to everyone. It is chosen from every leg on
// the day's matches read together (see backend/app/services/daily.py) and sits on its own staking run: after a
// miss the next day's stake rises to recover it, and after `max_misses` in a row the run starts again.
// Visitors see it at a £10 usual stake; an account can set its own, and gets the rest of Tonight's bundles.

const STAKE_KEY = 'daily-usual-stake'
const VISITOR_STAKE = 10

const STATUS = { won: ['Landed', 'text-pitch'], lost: ['Missed', 'text-red'], void: ['Void', 'text-ink-soft'] }

function Mark({ status }) {
  if (status === 'pending') return null
  const [label, tone] = STATUS[status] || STATUS.void
  return <span className={`shrink-0 text-xs font-bold uppercase tracking-wider ${tone}`}>{label}</span>
}

function publishTime(hourUtc) {
  const d = new Date()
  d.setUTCHours(hourUtc, 0, 0, 0)
  return d.toLocaleTimeString('en-GB', { hour: 'numeric', minute: '2-digit', hour12: true }).replace(':00', '').replace(' ', '')
}

// Where the run stands, in a sentence a casual reader follows.
function runLine(bundle, maxMisses) {
  if (bundle.step === 1) return 'First bet of a new run, so it is your usual stake.'
  const misses = bundle.step - 1
  return `${misses === 1 ? 'The last bundle' : `The last ${misses} bundles`} missed, so this one is ${bundle.multiplier.toFixed(2)}× your usual stake: enough that a win pays the run back and still makes a usual win. After ${maxMisses} misses in a row the run starts again at your usual stake.`
}

export default function DailyBundle({ className = '' }) {
  const { data, loading } = useApi(() => api.daily(), [])
  const custom = useCan('tonight_custom')
  const [usual, setUsual] = useState(VISITOR_STAKE)
  useEffect(() => {
    if (!custom) return setUsual(VISITOR_STAKE)
    try {
      const saved = Number(localStorage.getItem(STAKE_KEY))
      if (saved > 0) setUsual(saved)
    } catch {
      /* private window: keep the default */
    }
  }, [custom])
  const saveUsual = (v) => {
    setUsual(v)
    try {
      if (v > 0) localStorage.setItem(STAKE_KEY, String(v))
    } catch {
      /* not saved, still used */
    }
  }

  if (loading && !data) return <Loading rows={4} />
  if (!data) return null
  const { bundle, plan, today } = data
  const isToday = bundle?.day === today
  const waiting = !isToday && (data.no_bundle_today ? (
    <p><span className="font-semibold">No bundle today.</span> {data.no_bundle_today}</p>
  ) : (
    <p>Today's bundle is chosen from {publishTime(data.publish_hour_utc)}, once the day's prices and team news are in.</p>
  ))

  if (!bundle)
    return (
      <div className={`panel p-6 ${className}`}>
        <p className="text-sm font-semibold uppercase tracking-wider text-amber-dark">Bundle of the day</p>
        <div className="mt-2 text-ink-soft">{waiting}</div>
      </div>
    )

  const stake = (Number(usual) || 0) * bundle.multiplier
  const settled = bundle.status !== 'pending'
  return (
    <div className={`space-y-4 ${className}`}>
      {waiting && <div className="rounded-lg bg-amber-light/70 px-4 py-3 text-[15px] ring-1 ring-inset ring-amber/50">{waiting}</div>}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] lg:items-start">
        <div className="slip-shadow">
          <article className="perforated rounded-t-xl bg-paper">
            <header className="px-4 sm:px-5 pt-4 pb-3">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm text-ink-soft">
                <span className="font-semibold uppercase tracking-wider text-amber-dark">
                  {isToday ? "Today's bundle" : `${dayLabel(`${bundle.day}T12:00:00Z`)}'s bundle`}
                </span>
                <span>at <BookLink name={bundle.bookmaker} /></span>
                <span>chosen by {bundle.by_claude ? 'Claude' : 'our AI'}</span>
                {settled && <span className="ml-auto"><Mark status={bundle.status} /></span>}
              </div>
              {bundle.summary && <p className="mt-2 text-[15px] leading-relaxed">{bundle.summary}</p>}
            </header>
            <ol className="divide-y divide-dashed divide-ink/15 border-y border-dashed border-ink/15">
              {bundle.legs.map(({ tip_id, odds: price, reason, tip }) => (
                <li key={tip_id} className="px-4 sm:px-5 py-3">
                  <div className="flex items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-display font-extrabold text-[1.05rem] leading-tight tracking-tight">{pickLabel(tip, tip.fixture)}</p>
                      <Link to={matchPath(tip.fixture)} className="mt-0.5 flex items-center gap-1.5 text-sm text-ink-soft hover:text-ink">
                        <LeagueBadge league={tip.fixture.league} />
                        <span className="truncate">{tip.fixture.home.name} v {tip.fixture.away.name}</span>
                        <span className="shrink-0 num">· {kickoffTime(tip.fixture.kickoff)}</span>
                      </Link>
                    </div>
                    <Mark status={tip.status} />
                    <Price value={price} />
                  </div>
                  {reason && <p className="mt-1.5 text-sm leading-snug text-ink-soft">{reason}</p>}
                </li>
              ))}
            </ol>
            <footer className="px-4 sm:px-5 pt-3 pb-6 grid grid-cols-3 gap-3 items-end">
              <div className="min-w-0">
                <p className="text-sm text-ink-soft">Odds</p>
                <Price value={bundle.odds} board />
              </div>
              <div className="min-w-0">
                <p className="text-sm text-ink-soft">Stake</p>
                <p className="num text-xl sm:text-2xl font-bold truncate">{money(stake)}</p>
              </div>
              <div className="min-w-0 text-right">
                <p className="text-sm text-ink-soft">{settled ? (bundle.status === 'won' ? 'Returned' : 'Returns') : 'Returns'}</p>
                <p className={`num text-xl sm:text-2xl font-bold truncate ${bundle.status === 'lost' ? 'text-ink-soft line-through' : 'text-pitch'}`}>{money(stake * bundle.odds)}</p>
              </div>
            </footer>
          </article>
        </div>

        <div className="space-y-4">
          <div className="panel p-5 space-y-3">
            <p className="text-sm font-semibold uppercase tracking-wider text-amber-dark">The stake</p>
            <p className="text-[15px] leading-relaxed">{runLine(bundle, plan.max_misses)}</p>
            {custom ? (
              <label className="block text-sm text-ink-soft">
                Your usual stake
                <span className="mt-1 flex items-center rounded-lg border border-ink/20 bg-white px-3 focus-within:border-ink">
                  <span className="text-ink-soft">£</span>
                  <input type="number" min="1" step="1" inputMode="decimal" value={usual} onChange={(e) => saveUsual(e.target.value)} className="num w-full bg-transparent px-2 py-2 text-lg font-bold outline-none" />
                </span>
              </label>
            ) : (
              <p className="text-sm text-ink-soft">Shown for a £{VISITOR_STAKE} usual stake.</p>
            )}
            {data.this_run.length > 0 && (
              <p className="text-sm text-ink-soft">
                This run so far:{' '}
                {data.this_run.slice().reverse().map((b, i) => (
                  <span key={b.id} className={b.status === 'won' ? 'text-pitch font-semibold' : b.status === 'lost' ? 'text-red font-semibold' : ''}>
                    {i > 0 && <span className="text-ink-soft font-normal">, </span>}
                    {(STATUS[b.status] || STATUS.void)[0].toLowerCase()} at {b.odds.toFixed(2)}
                  </span>
                ))}
                .
              </p>
            )}
            {data.last_run && (
              <p className="text-sm text-ink-soft">
                The run before: {data.last_run.bundles} {data.last_run.bundles === 1 ? 'bundle' : 'bundles'}, {data.last_run.won ? 'ended with a win' : 'written off without a win'}.
              </p>
            )}
          </div>
          {custom ? (
            <Link to="/tonight" className="panel block p-5 transition hover:shadow-lift">
              <p className="font-display text-lg font-bold">More bets for tonight</p>
              <p className="mt-1 text-sm text-ink-soft">Pick the matches you're watching and a Safer, Standard or Big night target, and get up to three more bundles.</p>
            </Link>
          ) : (
            <JoinCard row title="Want more than one bet?">
              Members build bundles for the matches they're watching, at Safer, Standard or Big night odds, with their own stake.
            </JoinCard>
          )}
        </div>
      </div>
      <p className="text-sm text-ink-soft max-w-prose">
        A bundle needs every leg, so most days it misses. Raising the stake after a miss only pays off if a win comes;
        it can't make losing bets profitable. Stake only what you can afford to lose. 18+, free support at{' '}
        <a href="https://www.begambleaware.org" target="_blank" rel="noreferrer" className="underline">BeGambleAware.org</a>.
      </p>
    </div>
  )
}
