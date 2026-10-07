import { ago } from '../lib/format.js'

export const KIND = {
  fixtures: 'Fixtures and results',
  odds: 'Prices (The Odds API)',
  match_odds: 'Match prices (The Odds API)',
  markets: 'Prices, all markets',
  match_markets: 'Match prices',
  context: 'Match research',
  lineups: 'Line-ups',
  analysis: 'Claude analysis',
  chat: 'Claude reply',
}

export function runSummary(run) {
  if (run.provider === 'claude') {
    if (run.status === 'running') return 'Claude is thinking…'
    const c = run.details?.cost_usd
    const what = run.kind === 'analysis' ? (run.items ? 'Analysis recorded' : 'Replied') : run.items ? 'Replied with a revised analysis' : 'Replied'
    return c != null ? `${what}, cost ${c.toFixed(3)}` : what
  }
  const cost = run.provider === 'odds_api' ? `${run.credits_used} credit${run.credits_used === 1 ? '' : 's'}` : `${run.requests_made} request${run.requests_made === 1 ? '' : 's'}`
  if (run.status === 'running') return `Working… ${run.progress} of ${run.total}`
  const what =
    run.kind === 'fixtures' ? `${run.items} fixtures saved` :
    run.kind === 'odds' || run.kind === 'markets' ? `${run.items} matches priced` :
    run.kind === 'lineups' ? (run.items ? 'Line-ups saved' : 'No line-ups yet') :
    run.kind === 'context' ? `${run.items} of ${run.total} sections fetched` :
    run.items ? 'Prices updated' : 'No prices found'
  return `${what}, used ${cost}`
}

// Inline status for a sync the user just started: progress bar while running,
// then the outcome and what it cost.
export default function RunStatus({ run, error }) {
  if (error) {
    return <p className="text-sm text-red">{error.message}</p>
  }
  if (!run) return null
  const running = run.status === 'running'
  const tone = running ? 'text-ink-soft' : run.status === 'ok' ? 'text-pitch' : run.status === 'partial' ? 'text-amber-dark' : 'text-red'
  return (
    <div className="text-sm space-y-1" aria-live="polite">
      {running && (
        <div className="h-1.5 rounded-full bg-ink/10 overflow-hidden">
          <div
            className="h-full bg-amber transition-all"
            style={{ width: `${Math.max(6, (run.progress / Math.max(run.total, 1)) * 100)}%` }}
          />
        </div>
      )}
      <p className={tone}>
        <span className="font-semibold">{KIND[run.kind]}: </span>
        {runSummary(run)}
        {!running && run.finished_at && <span className="text-ink-faint"> ({ago(run.finished_at)})</span>}
      </p>
      {run.message && !running && <p className={run.status === 'ok' ? 'text-ink-soft' : 'text-red'}>{run.message}</p>}
    </div>
  )
}
