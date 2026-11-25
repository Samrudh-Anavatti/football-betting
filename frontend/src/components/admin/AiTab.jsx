import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi.js'
import { api } from '../../lib/api.js'
import { ago, odds, pct, pickLabel, shortDate, signed } from '../../lib/format.js'
import { runSummary } from '../RunStatus.jsx'
import { Empty, ErrorNote, Loading } from '../ui.jsx'
import { matchPath } from '../../lib/seo.js'

const usd = (x) => (x == null ? '–' : `$${x.toFixed(2)}`)

const RECORD_ROWS = [
  ['Picks settled', (r) => r.won + r.lost + r.void],
  ['Won, lost', (r) => `${r.won}–${r.lost}`],
  ['Profit (units)', (r) => signed(r.profit_units)],
  ['Return on stake', (r) => pct(r.roi)],
  ['Strike rate', (r) => pct(r.strike_rate, 0)],
  ['Average odds', (r) => r.avg_odds ?? '–'],
  ['Beat the closing price by', (r) => (r.clv == null ? '–' : `${pct(r.clv)} (${r.clv_samples})`)],
  ['Still pending', (r) => r.pending],
]

function Records({ records }) {
  return (
    <section className="panel overflow-hidden">
      <header className="px-5 py-3 border-b border-ink/10">
        <h3 className="text-2xl">AI vs our team</h3>
        <p className="text-sm text-ink-soft">
          The AI's suggestions are tracked at the best price when it made them, and settle like our team's picks. Beating the
          closing price is the best early sign of a real edge.
        </p>
      </header>
      <table className="w-full text-sm">
        <thead className="text-ink-soft">
          <tr>
            <th />
            <th className="font-medium text-right px-5 py-2">AI</th>
            <th className="font-medium text-right px-5 py-2">Our team</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ink/5">
          {RECORD_ROWS.map(([label, get]) => (
            <tr key={label}>
              <td className="px-5 py-1.5">{label}</td>
              <td className="px-5 text-right num text-base">{get(records.ai)}</td>
              <td className="px-5 text-right num text-base">{get(records.ivo)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function Scores({ scores }) {
  const row = (label, s) => {
    const better = s.ai != null && s.market != null ? s.ai < s.market : null
    return (
      <tr key={label}>
        <td className="px-5 py-1.5">{label}</td>
        <td className={`px-5 text-right num text-base ${better ? 'text-pitch font-semibold' : ''}`}>{s.ai?.toFixed(3) ?? '–'}</td>
        <td className="px-5 text-right num text-base">{s.market?.toFixed(3) ?? '–'}</td>
      </tr>
    )
  }
  return (
    <section className="panel overflow-hidden">
      <header className="px-5 py-3 border-b border-ink/10">
        <h3 className="text-2xl">Probabilities vs the market</h3>
        <p className="text-sm text-ink-soft">
          Brier score (lower is better) over {scores.matches} finished match{scores.matches === 1 ? '' : 'es'}, using
          the AI's last analysis before kick-off and the bookmakers' margin-free prices at that moment. The AI is only
          useful if it beats the market here over a decent sample (50+ matches).
        </p>
      </header>
      <table className="w-full text-sm">
        <thead className="text-ink-soft">
          <tr>
            <th />
            <th className="font-medium text-right px-5 py-2">AI</th>
            <th className="font-medium text-right px-5 py-2">Market</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ink/5">
          {row('Match result', scores.result)}
          {row('Over 2.5 goals', scores.over_2_5)}
          {row('Both teams score', scores.btts)}
        </tbody>
      </table>
    </section>
  )
}

// The latest bundle of the day, leg by leg, with the same by-hand settling the Picks tab has: for a leg the
// automatic settlement can't decide (a half win on a quarter line, a match the feed never finished). The bundle
// and the run's next stake are worked out again from the legs as they then stand.
function DailySettle() {
  const { data, error, reload } = useApi(() => api.daily(), [])
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(null)
  if (error) return <ErrorNote error={error} />
  const b = data?.bundle
  if (!b) return null
  const settle = async (tipId, status) => {
    setBusy(true)
    setFailed(null)
    try {
      await api.settleTip(tipId, status)
      await reload()
    } catch (e) {
      setFailed(e)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="panel px-5 py-4 space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-xl">Bundle of the day, {shortDate(b.day)}</h2>
        <span className="text-sm text-ink-soft">
          {b.status === 'pending' ? 'Waiting on its legs' : `Settled: ${b.status}`} · odds <span className="num">{odds(b.odds)}</span>
        </span>
      </div>
      <p className="text-sm text-ink-soft">
        Legs settle on their own at full time. Set one by hand here if it is stuck; the bundle follows its legs.
      </p>
      <ErrorNote error={failed} />
      <ul className="divide-y divide-ink/10">
        {b.legs.map((leg) => (
          <li key={leg.tip_id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2 text-sm">
            <Link to={matchPath(leg.tip.fixture)} className="min-w-0 flex-1 basis-56 hover:underline">
              <span className="font-semibold">{leg.tip.fixture.home.name} v {leg.tip.fixture.away.name}</span>
              <span className="block text-ink-soft">
                {pickLabel(leg.tip, leg.tip.fixture)} at <span className="num">{odds(leg.odds)}</span>
                {leg.tip.fixture.home_goals != null && ` · finished ${leg.tip.fixture.home_goals}–${leg.tip.fixture.away_goals}`}
              </span>
            </Link>
            <select
              className="input py-1 w-auto"
              value={leg.tip.status}
              disabled={busy}
              aria-label={`Settle ${leg.tip.fixture.home.name} v ${leg.tip.fixture.away.name} by hand`}
              onChange={(e) => settle(leg.tip_id, e.target.value)}
            >
              <option value="pending">Pending</option>
              <option value="won">Won</option>
              <option value="lost">Lost</option>
              <option value="void">Void</option>
            </select>
          </li>
        ))}
      </ul>
    </section>
  )
}

// Each AI provider's month against its budget, and the calls made for the bundle of the day. The figures are our
// own count from the tokens each call used, not the provider's balance.
function Meter({ name, s, note }) {
  const share = Math.min(1, s.spent_usd / Math.max(s.limit_usd, 0.01))
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-end gap-x-3">
        <p>
          <span className="num text-3xl font-bold">{usd(s.left_usd)}</span>
          <span className="text-ink-soft"> left of {usd(s.limit_usd)}</span>
        </p>
        <span className="text-sm text-ink-soft sm:ml-auto">
          {name}: {s.model}
          {!s.configured && ', not connected'}
        </span>
      </div>
      <div className="h-2.5 rounded-full bg-ink/10 overflow-hidden" role="meter" aria-valuenow={s.spent_usd} aria-valuemin={0} aria-valuemax={s.limit_usd} aria-label={`${name} budget used`}>
        <div className={`h-full ${share > 0.9 ? 'bg-red' : share > 0.7 ? 'bg-amber' : 'bg-pitch'}`} style={{ width: `${share * 100}%` }} />
      </div>
      <p className="text-sm text-ink-soft">{usd(s.spent_usd)} spent this month. {note}</p>
    </div>
  )
}

function DailySpend() {
  const { data, error, reload } = useApi(() => api.dailyAdmin(), [])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const build = async () => {
    setBusy(true)
    setMessage(null)
    try {
      await api.dailyBuild()
      setMessage("Asked for today's bundle; it takes a minute or two. Reload to see the call below.")
    } catch (e) {
      setMessage(e.message)
    }
    setBusy(false)
    reload?.()
  }
  return (
    <section className="panel px-5 py-4 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl">AI budgets this month</h2>
        <button type="button" onClick={build} disabled={busy} className="btn-ghost ml-auto text-sm">Build today's bundle now</button>
      </div>
      {message && <p className="text-sm text-ink-soft">{message}</p>}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Meter name="Claude" s={data.spend.claude} note="Picks the bundle of the day. Limit: CLAUDE_MONTHLY_BUDGET_USD; key: ANTHROPIC_API_KEY." />
        <Meter name="Luna" s={data.spend.luna} note="Match reports, and the bundle of the day when Claude can't. Limit: AI_MONTHLY_BUDGET_USD." />
      </div>
      {data.calls.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-ink-soft">
              <tr><th className="py-1 pr-3 font-medium">Day</th><th className="pr-3 font-medium">Model</th><th className="pr-3 font-medium">Outcome</th><th className="pr-3 font-medium text-right">Tokens in / out</th><th className="font-medium text-right">Cost</th></tr>
            </thead>
            <tbody className="divide-y divide-ink/10">
              {data.calls.map((c) => (
                <tr key={c.id} title={c.note || ''}>
                  <td className="py-1.5 pr-3 num">{c.day}</td>
                  <td className="pr-3">{c.model || c.provider}</td>
                  <td className="pr-3">{c.outcome}{c.note ? `: ${c.note}` : ''}</td>
                  <td className="pr-3 num text-right">{c.input_tokens.toLocaleString()} / {c.output_tokens.toLocaleString()}</td>
                  <td className="num text-right">{usd(c.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default function AiTab() {
  const { data, loading, error } = useApi(() => api.aiSummary(), [])
  if (loading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  const share = Math.min(1, data.budget.spent_usd / Math.max(data.budget.limit_usd, 0.01))

  return (
    <div className="space-y-6">
      <DailySettle />
      <DailySpend />
      <section className="panel px-5 py-4 space-y-2">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
          <p>
            <span className="num text-4xl font-bold">{usd(data.budget.spent_usd)}</span>
            <span className="text-ink-soft"> of {usd(data.budget.limit_usd)} used this month</span>
          </p>
          <span className="text-sm text-ink-soft sm:ml-auto">
            {data.model} on {data.provider}
            {!data.configured && ', not connected'}
          </span>
        </div>
        <div className="h-2.5 rounded-full bg-ink/10 overflow-hidden" role="meter" aria-valuenow={data.budget.spent_usd} aria-valuemin={0} aria-valuemax={data.budget.limit_usd} aria-label="AI budget used">
          <div className={`h-full ${share > 0.9 ? 'bg-red' : share > 0.7 ? 'bg-amber' : 'bg-pitch'}`} style={{ width: `${share * 100}%` }} />
        </div>
        <p className="text-sm text-ink-soft">
          The Analyse button stops working once the budget is used. Change it with the AI_MONTHLY_BUDGET_USD setting.
        </p>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Records records={data.records} />
        <Scores scores={data.scores} />
      </div>

      <section className="panel overflow-hidden">
        <header className="px-5 py-3 border-b border-ink/10">
          <h3 className="text-2xl">Recent analyses</h3>
        </header>
        {data.recent.length === 0 ? (
          <div className="p-5">
            <Empty title="No analyses yet">Open an upcoming match and use Analyse with AI.</Empty>
          </div>
        ) : (
          <ul className="divide-y divide-ink/5 text-sm">
            {data.recent.map((t) => (
              <li key={t.thread_id} className="px-5 py-2.5 grid grid-cols-[1fr_auto] sm:grid-cols-[1fr_8rem_6rem_5rem] gap-x-3 items-center">
                <Link to={matchPath(t.fixture)} className="font-medium hover:underline truncate">
                  {t.fixture.home.name} v {t.fixture.away.name}
                  <span className="text-ink-faint font-normal"> · {shortDate(t.fixture.kickoff)}</span>
                </Link>
                <span className="text-ink-soft hidden sm:block">
                  {t.created_by}, {ago(t.created_at)}
                </span>
                <span className="text-ink-soft hidden sm:block">
                  {t.predictions} analys{t.predictions === 1 ? 'is' : 'es'}
                </span>
                <span className="num text-base text-right">{usd(t.cost_usd)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {data.runs.some((r) => r.status === 'error' || r.status === 'partial') && (
        <section className="panel px-5 py-3 text-sm space-y-1">
          <h3 className="text-lg">Recent problems</h3>
          {data.runs
            .filter((r) => r.status === 'error' || r.status === 'partial')
            .map((r) => (
              <p key={r.id} className="text-red">
                {ago(r.started_at)}, {r.scope}: {r.message || runSummary(r)}
              </p>
            ))}
        </section>
      )}
    </div>
  )
}
