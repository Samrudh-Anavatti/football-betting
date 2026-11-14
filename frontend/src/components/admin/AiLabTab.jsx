import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi.js'
import { api } from '../../lib/api.js'
import { ago, dayLabel, kickoffTime, money, odds, pct, pickLabel, shortDate, signed, teamify } from '../../lib/format.js'
import { matchPath } from '../../lib/seo.js'
import { BundleHistory, BundleSlip, Ladder, Stat } from '../../pages/Staking.jsx'
import { ErrorNote, Freshness, LeagueBadge, Loading, Price, SectionHead } from '../ui.jsx'

// The AI Lab: the AI's own recovery-ladder staking test and the arbitrage scanner. Admin → AI Lab since 2026-11-14,
// when the public-facing AI staking became Tonight's bundles (pages/Tonight.jsx).

function MatchLine({ fixture }) {
  return (
    <Link to={matchPath(fixture)} className="flex items-center gap-1.5 text-sm text-ink-soft hover:text-ink min-w-0">
      <LeagueBadge league={fixture.league} />
      <span className="truncate">
        {fixture.home.name} v {fixture.away.name}
      </span>
      <span className="shrink-0 num">
        · {dayLabel(fixture.kickoff)}, {kickoffTime(fixture.kickoff)}
      </span>
    </Link>
  )
}

// ── AI staking ───────────────────────────────────────────────────────────────

// The question the test answers: do the AI's legs land more often than their prices say?
function LegRecord({ legs }) {
  if (!legs.settled)
    return (
      <div className="panel p-4 text-sm text-ink-soft">
        No legs settled yet ({legs.pending} waiting). Once they do, this compares how often they land with what their
        prices implied.
      </div>
    )
  const beat = legs.hit_rate - legs.implied_rate
  return (
    <div className="panel p-4 space-y-2">
      <p className="text-sm text-ink-soft">The AI's legs on their own</p>
      <p className="text-[15px]">
        Landed <span className="num font-semibold">{legs.won}</span> of <span className="num">{legs.settled}</span>{' '}
        (<span className="num font-semibold">{pct(legs.hit_rate, 0)}</span>). Their prices implied{' '}
        <span className="num">{pct(legs.implied_rate, 0)}</span>, the AI expected <span className="num">{pct(legs.ai_rate, 0)}</span>.
      </p>
      <p className={`text-sm font-semibold ${beat > 0 ? 'text-pitch' : 'text-red'}`}>
        {beat > 0 ? 'Beating' : 'Behind'} the prices by {pct(Math.abs(beat), 1)} · 1 unit on each: {signed(legs.profit_units)} units
      </p>
      <p className="text-xs text-ink-soft">
        The plan can only profit if this stays above the prices. Under about 100 legs, it's mostly luck.
      </p>
    </div>
  )
}

function OpenLegs({ legs }) {
  if (!legs.length) return <p className="text-ink-soft text-sm">No legs for matches in the next 48 hours yet.</p>
  return (
    <ol className="panel divide-y divide-ink/5">
      {legs.map((t) => (
        <li key={t.id} className="px-4 py-2.5 flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="font-semibold truncate">{pickLabel(t, t.fixture)}</p>
            <MatchLine fixture={t.fixture} />
          </div>
          <span className="text-sm text-ink-soft num shrink-0">AI {pct(t.ai_probability, 0)}</span>
          <div className="text-right shrink-0">
            <Price value={t.current_odds ?? t.odds} />
            {t.current_odds != null && t.current_odds !== t.odds && (
              <p className="text-xs text-ink-soft num">was {odds(t.odds)}</p>
            )}
          </div>
        </li>
      ))}
    </ol>
  )
}

function PlanSettings({ plan, onSaved }) {
  const [form, setForm] = useState({ base_stake: plan.base_stake, target_odds: plan.target_odds, bank: plan.bank })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const save = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onSaved(await api.aiLabUpdatePlan(form))
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  const field = (key, label, step) => (
    <label className="block">
      <span className="label">{label}</span>
      <input type="number" step={step} min="0" className="input num" value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })} />
    </label>
  )
  return (
    <form onSubmit={save} className="panel p-4 space-y-3">
      <div className="grid grid-cols-3 gap-3">
        {field('base_stake', 'Base stake', '0.5')}
        {field('target_odds', 'Target odds', '0.1')}
        {field('bank', 'Bank', '10')}
      </div>
      <ErrorNote error={error} />
      <button className="btn-ghost" disabled={busy}>{busy ? 'Saving…' : 'Save plan'}</button>
    </form>
  )
}

function AiStaking() {
  const { data, error, loading, reload } = useApi(() => api.aiLabStaking(), [])
  const [state, setState] = useState(null)
  const [actionError, setActionError] = useState(null)
  const d = state || data
  if (loading && !d) return <Loading rows={4} />
  if (error && !d) return <ErrorNote error={error} />
  const { plan, run, current, history, stats, legs, open_legs: openLegs, waiting_legs: waiting } = d
  const act = async (fn) => {
    setActionError(null)
    try {
      setState(await fn())
    } catch (err) {
      setActionError(err)
    }
  }
  const removeCurrent = async () => {
    if (!window.confirm('Delete the live AI bundle? Its legs go back to the open list.')) return
    await act(async () => {
      await api.aiLabDeleteBundle(current.id)
      setState(null)
      await reload()
      return null
    })
  }

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] items-start">
        <div className="space-y-3">
          {current ? (
            <>
              <BundleSlip
                bundle={current}
                losses={run.losses}
                onSettle={(tip, status) =>
                  act(async () => {
                    await api.settleTip(tip.id, status)
                    return api.aiLabStaking()
                  })
                }
              />
              <button type="button" className="btn-ghost text-sm" onClick={removeCurrent}>Delete this bundle</button>
            </>
          ) : (
            <div className="panel px-5 py-8 text-center space-y-3">
              <p className="font-display text-xl font-bold">No live bundle</p>
              <p className="text-ink-soft max-w-prose mx-auto">
                The schedule builds one as soon as legs kicking off in the next 48 hours reach about {odds(plan.target_odds)}.
                Run {run.number}, bet {run.step}: stake about <span className="num font-semibold text-ink">{money(run.next_stake)}</span>.
              </p>
              {waiting.count > 0 && (
                <p className="text-sm max-w-prose mx-auto">
                  <span className="num font-semibold">{waiting.count}</span> leg{waiting.count === 1 ? '' : 's'} waiting for
                  later matches; the first can go in a bundle from {dayLabel(waiting.usable_from)}, {kickoffTime(waiting.usable_from)}.
                </p>
              )}
              <button type="button" className="btn-primary" onClick={() => act(api.aiLabBuild)}>Build now</button>
            </div>
          )}
          <ErrorNote error={actionError} />
        </div>
        <LegRecord legs={legs} />
      </div>

      <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
        <Stat label="Profit" value={money(stats.profit)} tone={stats.profit > 0 ? 'text-pitch' : stats.profit < 0 ? 'text-red' : ''} />
        <Stat label="Bank" value={money(stats.bank_now)} />
        <Stat label="Bundles won / lost" value={`${stats.won}–${stats.lost}`} />
        <Stat label="Longest losing run" value={stats.longest_losing_streak} />
      </div>

      <section>
        <SectionHead title="Open legs" count={openLegs.length || null} />
        <OpenLegs legs={openLegs} />
      </section>

      <section>
        <SectionHead title="Every bundle" count={history.length || null} />
        {history.length ? <BundleHistory history={history} /> : <p className="text-ink-soft text-sm">Settled bundles appear here.</p>}
      </section>

      <section>
        <SectionHead title="Plan" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 items-start">
          <div className="space-y-3">
            <p className="text-[15px] text-ink-soft max-w-prose">
              The AI's own virtual plan, separate from ours: a win makes {money(plan.target_profit)}; {money(plan.bank)}{' '}
              covers {plan.survivable_losses} losses in a row. Changing it affects the next bundle, not the live one.
            </p>
            <PlanSettings key={`${plan.base_stake}-${plan.target_odds}-${plan.bank}`} plan={plan} onSaved={setState} />
          </div>
          <Ladder plan={plan} step={current ? current.step : run.step} />
        </div>
      </section>
    </div>
  )
}

// ── Arbitrage ────────────────────────────────────────────────────────────────

function ArbCard({ a, total }) {
  return (
    <li className="panel p-4 space-y-2">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="font-semibold">
          {a.market}
          {a.line != null && ` ${a.line}`}
        </p>
        <span className={`num font-bold ${a.suspect ? 'text-amber-dark' : 'text-pitch'}`}>{pct(a.profit, 2)}</span>
        {a.suspect && <span className="text-xs font-semibold uppercase tracking-wider text-amber-dark">Check it: likely a bad price</span>}
        <span className="ml-auto"><Freshness at={a.prices_at} warnAfter={1} staleAfter={6} prefix="Prices" /></span>
      </div>
      <MatchLine fixture={a.fixture} />
      <ul className="text-sm divide-y divide-ink/5">
        {a.legs.map((l) => (
          <li key={l.value} className="py-1.5 flex items-center gap-3">
            <span className="flex-1 min-w-0 truncate">{teamify(l.value, a.fixture)}</span>
            <span className="text-ink-soft shrink-0">{l.bookmaker}</span>
            <span className="num w-12 text-right shrink-0">{odds(l.price)}</span>
            <span className="num w-20 text-right font-semibold shrink-0">{money(total * l.share)}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-ink-soft">
        Returns {money(total * (1 + a.profit))} whichever wins. Seen since {ago(a.first_seen)}
        {a.best_profit > a.profit && `, best ${pct(a.best_profit, 2)}`}.
      </p>
    </li>
  )
}

function Arbitrage() {
  const { data, error, loading } = useApi(() => api.aiLabArbs(), [])
  const [total, setTotal] = useState(100)
  if (loading && !data) return <Loading rows={4} />
  if (error) return <ErrorNote error={error} />
  const { live, recent, stats, scanned_at: scannedAt } = data
  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] items-start">
        <div className="space-y-3 text-[15px] max-w-prose">
          <p>
            Markets where the best prices across our five bookmakers add up to under 100%: back every outcome in these
            proportions and the return is the same whatever happens. Found in the prices we already pull, so no extra
            cost.
          </p>
          <p className="text-sm text-ink-soft">
            Our prices can be up to an hour old (minutes near kick-off), so check each one at the bookmaker before
            staking. Bookmakers can void bets on obvious errors and often restrict accounts that bet arbs.
          </p>
        </div>
        <div className="panel p-4 space-y-2">
          <label className="block">
            <span className="label">Total stake</span>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft">£</span>
              <input type="number" min="1" step="10" inputMode="decimal" className="input pl-7 num text-lg" value={total}
                onChange={(e) => setTotal(Number(e.target.value))} />
            </div>
          </label>
          <p className="text-sm text-ink-soft">{scannedAt ? `Last scanned ${ago(scannedAt)}.` : 'Not scanned yet.'}</p>
        </div>
      </div>

      <section>
        <SectionHead title="Open now" count={live.length || null} />
        {live.length ? (
          <ol className="grid grid-cols-1 gap-3 lg:grid-cols-2">{live.map((a) => <ArbCard key={a.id} a={a} total={total} />)}</ol>
        ) : (
          <p className="text-ink-soft text-sm">None in the latest prices.</p>
        )}
      </section>

      <section>
        <SectionHead title={`Last ${stats.days} days`} count={stats.closed || null} />
        <p className="text-sm text-ink-soft mb-3">
          {stats.genuine} of {stats.closed} looked genuine
          {stats.median_minutes != null && <>, visible for a median of {stats.median_minutes} min</>}
          {stats.average_profit != null && <>, averaging {pct(stats.average_profit, 2)} at best</>}.
        </p>
        {recent.length > 0 && (
          <ol className="panel divide-y divide-ink/5 text-sm">
            {recent.map((a) => (
              <li key={a.id} className="px-4 py-2 flex items-center gap-3">
                <span className="w-16 shrink-0 text-ink-soft num hidden sm:block">{shortDate(a.first_seen)}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">
                    {a.market}
                    {a.line != null && ` ${a.line}`}
                    {a.suspect && <span className="ml-2 text-xs text-amber-dark">likely a bad price</span>}
                  </p>
                  <p className="truncate text-ink-soft">{a.fixture.home.name} v {a.fixture.away.name}</p>
                </div>
                <span className="num shrink-0 text-ink-soft">{a.legs.map((l) => odds(l.price)).join(' / ')}</span>
                <span className="num w-16 text-right font-semibold shrink-0">{pct(a.best_profit, 2)}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  )
}

const TABS = [
  { key: 'staking', label: 'AI staking ladder', el: AiStaking },
  { key: 'arbs', label: 'Arbitrage', el: Arbitrage },
]

export default function AiLabTab() {
  const [key, setKey] = useState(TABS[0].key)
  const active = TABS.find((t) => t.key === key) || TABS[0]
  const Tab = active.el
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <nav className="segmented" aria-label="AI Lab sections">
          {TABS.map((t) => (
            <button key={t.key} type="button" aria-current={t.key === active.key ? 'page' : undefined}
              onClick={() => setKey(t.key)} className={`segment px-4 ${t.key === active.key ? 'segment-on' : ''}`}>
              {t.label}
            </button>
          ))}
        </nav>
        <p className="text-sm text-ink-soft">
          The ladder is the test of whether the AI's legs beat their prices; what people use is{' '}
          <Link to="/tonight" className="link">Tonight's bundles</Link>.
        </p>
      </div>
      <Tab />
    </div>
  )
}
