import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi.js'
import { api } from '../../lib/api.js'
import { ago, pct, shortDate, signed } from '../../lib/format.js'
import { runSummary } from '../RunStatus.jsx'
import { Empty, ErrorNote, Loading } from '../ui.jsx'

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
        <h3 className="text-2xl">AI vs Ivo</h3>
        <p className="text-sm text-ink-soft">
          The AI's suggestions are tracked at the best price when it made them, and settle like Ivo's picks. Beating the
          closing price is the best early sign of a real edge.
        </p>
      </header>
      <table className="w-full text-sm">
        <thead className="text-ink-soft">
          <tr>
            <th />
            <th className="font-medium text-right px-5 py-2">AI</th>
            <th className="font-medium text-right px-5 py-2">Ivo</th>
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

export default function AiTab() {
  const { data, loading, error } = useApi(() => api.aiSummary(), [])
  if (loading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  const share = Math.min(1, data.budget.spent_usd / Math.max(data.budget.limit_usd, 0.01))

  return (
    <div className="space-y-6">
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

      <div className="grid gap-6 lg:grid-cols-2">
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
                <Link to={`/match/${t.fixture.id}`} className="font-medium hover:underline truncate">
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
