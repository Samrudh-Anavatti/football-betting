import { useState } from 'react'
import BookLink from '../components/BookLink.jsx'
import { Link } from 'react-router-dom'
import JoinCard from '../components/JoinCard.jsx'
import { SubNav } from '../components/Shell.jsx'
import { ErrorNote, LeagueBadge, Loading, Price, SectionHead } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { useCan } from '../lib/access.js'
import { api } from '../lib/api.js'
import { useAuth } from '../lib/auth.jsx'
import { dayLabel, kickoffTime, money, odds, pct, pickLabel, shortDate } from '../lib/format.js'
import { matchPath } from '../lib/seo.js'
import { bundleWinChance, ladder, streakChance } from '../lib/staking.js'
import { SAMPLE_PLAN } from '../lib/stakingSample.js'

const STAKE_KEY = 'fb.stake'

const RESULT = {
  won: ['W', 'bg-pitch text-white'],
  lost: ['L', 'bg-red text-white'],
  void: ['V', 'bg-ink/10 text-ink-soft'],
  pending: ['·', 'bg-ink/[0.06] text-ink-soft'],
}

export function ResultMark({ status }) {
  const [letter, tone] = RESULT[status] || RESULT.pending
  return (
    <span className={`h-6 w-6 shrink-0 grid place-items-center rounded text-xs font-bold ${tone}`} aria-label={status}>
      {letter}
    </span>
  )
}

// The live bundle, printed as a slip: each pick with its price, then the combined odds, stake and return.
// `onSettle(tip, status)`: admins can settle a leg by hand once its match has kicked off, for markets the
// automatic settlement can't decide (or a result the data provider never sent).
export function BundleSlip({ bundle, scale = 1, losses, onSettle }) {
  return (
    <div className="slip-shadow">
      <article className="perforated rounded-t-xl bg-paper">
        <header className="px-4 pt-3.5 pb-2 flex flex-wrap items-baseline gap-x-3 text-sm text-ink-soft">
          <span className="font-display font-bold text-ink">
            Run {bundle.run}, bet {bundle.step}
          </span>
          {losses > 0 && <span>recovering {money(losses * scale)}</span>}
          {bundle.bookmaker && <span>at <BookLink name={bundle.bookmaker} /></span>}
          <span className="ml-auto">Placed {shortDate(bundle.created_at)}</span>
        </header>
        <ol className="divide-y divide-dashed divide-ink/15 border-y border-dashed border-ink/15">
          {bundle.legs.map(({ tip_id, odds: price, tip }) => (
            <li key={tip_id} className="px-4 py-2.5 flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="font-display font-extrabold text-[1.1rem] leading-tight tracking-tight truncate">
                  {pickLabel(tip, tip.fixture)}
                </p>
                <Link to={matchPath(tip.fixture)} className="mt-0.5 flex items-center gap-1.5 text-sm text-ink-soft hover:text-ink">
                  <LeagueBadge league={tip.fixture.league} />
                  <span className="truncate">
                    {tip.fixture.home.name} v {tip.fixture.away.name}
                  </span>
                  <span className="shrink-0 num">
                    · {dayLabel(tip.fixture.kickoff)}, {kickoffTime(tip.fixture.kickoff)}
                  </span>
                </Link>
              </div>
              {tip.status !== 'pending' && <ResultMark status={tip.status} />}
              {tip.status === 'pending' && onSettle && new Date(tip.fixture.kickoff) < Date.now() && (
                <select
                  className="input py-1 w-auto text-sm"
                  defaultValue=""
                  aria-label="Settle this leg"
                  onChange={(e) => e.target.value && onSettle(tip, e.target.value)}
                >
                  <option value="">Settle…</option>
                  <option value="won">Won</option>
                  <option value="lost">Lost</option>
                  <option value="void">Void</option>
                </select>
              )}
              <Price value={price} />
            </li>
          ))}
        </ol>
        <footer className="px-4 pt-3 pb-6 grid grid-cols-3 gap-3 items-end">
          <div className="min-w-0">
            <p className="text-sm text-ink-soft">Odds</p>
            <Price value={bundle.odds} board />
          </div>
          <div className="min-w-0">
            <p className="text-sm text-ink-soft">Stake</p>
            <p className="num text-xl sm:text-2xl font-bold truncate">{money(bundle.stake * scale)}</p>
          </div>
          <div className="min-w-0 text-right">
            <p className="text-sm text-ink-soft">Returns</p>
            <p className="num text-xl sm:text-2xl font-bold text-pitch truncate">{money(bundle.returns * scale)}</p>
          </div>
        </footer>
      </article>
    </div>
  )
}

export function Stat({ label, value, tone = '' }) {
  return (
    <div className="panel px-4 py-3">
      <p className="text-sm text-ink-soft">{label}</p>
      <p className={`num text-2xl sm:text-3xl font-semibold ${tone}`}>{value}</p>
    </div>
  )
}

// The bets of a run that keeps losing, at the target odds, until the bank runs out.
export function Ladder({ plan, scale = 1, step }) {
  const rows = ladder({ ...plan, base_stake: plan.base_stake * scale, bank: plan.bank * scale })
  return (
    <ol className="panel divide-y divide-ink/5 text-sm">
      <li className="px-4 py-2 flex gap-3 text-ink-soft">
        <span className="w-12">Bet</span>
        <span className="flex-1 text-right">Stake</span>
        <span className="flex-1 text-right">Lost before it</span>
        <span className="flex-1 text-right">Win returns</span>
      </li>
      {rows.map((r) => (
        <li
          key={r.step}
          className={`px-4 py-1.5 flex gap-3 num ${r.step === step ? 'bg-amber-light font-semibold' : ''} ${r.affordable ? '' : 'text-red'}`}
        >
          <span className="w-12">{r.step}</span>
          <span className="flex-1 text-right">{money(r.stake)}</span>
          <span className="flex-1 text-right">{money(r.lostBefore)}</span>
          <span className="flex-1 text-right">{r.affordable ? money(r.stake * plan.target_odds) : 'bank out'}</span>
        </li>
      ))}
    </ol>
  )
}

// Settled bundles, newest first.
export function BundleHistory({ history, scale = 1 }) {
  return (
    <ol className="panel divide-y divide-ink/5">
      {history.map((b) => (
        <li key={b.id} className="flex items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2.5 text-sm">
          <span className="hidden sm:block w-16 shrink-0 text-ink-soft num">{shortDate(b.created_at)}</span>
          <div className="min-w-0 flex-1">
            <p className="font-semibold">
              Run {b.run}, bet {b.step}
            </p>
            <p className="truncate text-ink-soft">{b.legs.map((l) => pickLabel(l.tip, l.tip.fixture)).join(' · ')}</p>
          </div>
          <span className="w-10 shrink-0 text-right num">{odds(b.odds)}</span>
          <span className="w-16 shrink-0 text-right num">{money(b.stake * scale)}</span>
          <ResultMark status={b.status} />
          <span className={`w-20 shrink-0 text-right num font-semibold ${b.profit > 0 ? 'text-pitch' : b.profit < 0 ? 'text-red' : 'text-ink-soft'}`}>
            {b.profit > 0 ? '+' : ''}
            {money(b.profit * scale)}
          </span>
        </li>
      ))}
    </ol>
  )
}

function PlanView({ data, hitRate, days }) {
  const { plan, run, current, history, previous_run: last } = data
  const [stake, setStake] = useState(() => {
    try {
      return Number(localStorage.getItem(STAKE_KEY)) || plan.base_stake
    } catch {
      return plan.base_stake
    }
  })
  const changeStake = (v) => {
    setStake(v)
    try {
      localStorage.setItem(STAKE_KEY, String(v))
    } catch {
      /* private mode: keep it for this visit */
    }
  }
  const scale = stake > 0 ? stake / plan.base_stake : 1
  const legs = current ? current.legs.length : 3
  const winChance = hitRate == null ? null : bundleWinChance(hitRate, legs)
  const wipeout = winChance == null ? null : streakChance(winChance, plan.survivable_losses + 1)

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] items-start">
        <div className="space-y-3">
          {current ? (
            <BundleSlip bundle={current} scale={scale} losses={run.losses} />
          ) : (
            <div className="panel px-5 py-8 text-center">
              <p className="font-display text-xl font-bold">Next bundle coming soon</p>
              <p className="mt-1 text-ink-soft max-w-prose mx-auto">
                We bundle the picks once the day's are in. Run {run.number}, bet {run.step}: the stake will be about{' '}
                <span className="num font-semibold text-ink">{money(run.next_stake * scale)}</span>
                {run.losses > 0 && <> to win back {money(run.losses * scale)} and make the profit</>}.
              </p>
            </div>
          )}
        </div>
        <div className="panel p-4 space-y-3">
          <label className="block">
            <span className="label">Your starting stake</span>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft">£</span>
              <input
                type="number"
                min="1"
                step="1"
                inputMode="decimal"
                className="input pl-7 num text-lg"
                value={stake}
                onChange={(e) => changeStake(Number(e.target.value))}
              />
            </div>
          </label>
          <p className="text-sm text-ink-soft">
            Every stake on this page scales with it. Each win finishes a run{' '}
            <span className="num font-semibold text-pitch">{money(plan.target_profit * scale)}</span> up. A{' '}
            {money(plan.bank * scale)} bank covers <span className="num font-semibold text-ink">{plan.survivable_losses}</span>{' '}
            losses in a row.
          </p>
        </div>
      </div>

      <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
        <Stat label="Run" value={run.number} />
        <Stat label="Bet in this run" value={current ? current.step : run.step} />
        <Stat label="Lost so far this run" value={money(run.losses * scale)} tone={run.losses > 0 ? 'text-red' : ''} />
        <Stat label={current ? 'This bet returns' : 'Next stake'} value={money((current ? current.returns : run.next_stake) * scale)} />
      </div>

      <section>
        <SectionHead title="How it works" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 items-start">
          <div className="space-y-3 text-[15px] leading-relaxed max-w-prose">
            <p>
              We combine our picks into one bet at odds of about {odds(plan.target_odds)}. A win makes{' '}
              {money(plan.target_profit * scale)} and starts a new run at {money(plan.base_stake * scale)}.
            </p>
            <p>
              A loss raises the next stake so that its win pays back everything the run has lost and still makes the{' '}
              {money(plan.target_profit * scale)}. At {odds(plan.target_odds)} that's about ×{plan.multiplier.toFixed(2)}{' '}
              each time; the exact stake depends on each bundle's real odds.
            </p>
            {winChance != null && (
              <p>
                Over the last {days} days our picks have landed {pct(hitRate, 0)} of the time. At that rate a {Math.round(legs)}-pick bundle
                wins about {pct(winChance, 0)} of the time, and {plan.survivable_losses + 1} losses in a row, enough to
                empty the bank, happens in about {pct(wipeout, 1)} of runs.
              </p>
            )}
            <p className="text-ink-soft">
              No staking plan creates an edge: it only works if the picks beat the odds. Stake only what you can afford to
              lose. 18+, free support at BeGambleAware.org.
            </p>
          </div>
          <Ladder plan={plan} scale={scale} step={current ? current.step : run.step} />
        </div>
      </section>

      {data.preview && (
        <JoinCard row title="The run so far is for members">
          You're seeing the live bundle and its stake. Members also get every bundle in this run and how the last one
          ended.
        </JoinCard>
      )}
      <section className={data.preview ? 'hidden' : ''}>
        <SectionHead title="This run" count={history.length || null} />
        {history.length === 0 ? (
          <p className="text-ink-soft">No bundle has settled in this run yet. A win ends the run and starts the next.</p>
        ) : (
          <BundleHistory history={history} scale={scale} />
        )}
        {last && (
          <p className="mt-3 text-sm text-ink-soft">
            Before it, run {last.number} finished on {shortDate(last.ended_at)} after {last.bundles} bundle
            {last.bundles === 1 ? '' : 's'},{' '}
            <span className="num font-semibold text-ink">{money(Math.abs(last.profit) * scale)}</span>{' '}
            {last.profit < 0 ? 'down' : 'up'}.
          </p>
        )}
      </section>
    </div>
  )
}

// The odds of a wipeout are only worth showing when the record's window has enough settled picks to estimate a hit
// rate from.
const MIN_PICKS = 20

function Members() {
  const plan = useApi(() => api.staking(), [])
  const record = useApi(() => api.record(), [])
  if (plan.loading && !plan.data) return <Loading rows={4} />
  if (plan.error) return <ErrorNote error={plan.error} />
  const r = record.data
  const hitRate = r && r.won + r.lost >= MIN_PICKS ? r.strike_rate : null
  return <PlanView data={plan.data} hitRate={hitRate} days={r?.days} />
}

// Without the `staking` feature: the page's shape under a blur, filled with made-up data (lib/stakingSample.js),
// and the way in. The real plan is never sent to them (a blur only hides what the browser has).
function Preview() {
  return (
    <div className="relative">
      <div aria-hidden inert="" data-nosnippet="" className="pointer-events-none select-none blur-[6px] opacity-60">
        <PlanView data={SAMPLE_PLAN} hitRate={0.66} days={14} />
      </div>
      <div className="absolute inset-x-0 top-10 sm:top-24 flex justify-center px-2">
        <JoinCard title="Our staking plan" className="max-w-md mx-auto">
          Our picks combined into bets at around 6.00, each stake worked out for you. Follow the live bundle, scaled
          to your own stake, with every result on the record.
        </JoinCard>
      </div>
    </div>
  )
}

// The two kinds of bundle share a section of the site: the AI's for tonight, and our own staking plan.
export const BUNDLE_TABS = [
  ['/tonight', "Tonight's AI bundles"],
  ['/staking', 'Our staking plan'],
]

export default function Staking() {
  const { checking } = useAuth()
  const can = useCan('staking')
  return (
    <section className="space-y-6">
      <div data-tour="staking" className="space-y-4">
        <SubNav tabs={BUNDLE_TABS} />
        <h1 className="text-4xl sm:text-5xl leading-none">Our staking plan</h1>
        <p className="max-w-prose text-[17px] text-ink-soft leading-relaxed">
          Our own picks combined into one bet at about 6.00. After a loss the next stake rises just enough that a win
          pays the run back and still makes the profit.
        </p>
      </div>
      {checking ? <Loading rows={4} /> : can ? <Members /> : <Preview />}
    </section>
  )
}
