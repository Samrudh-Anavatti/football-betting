import { ago } from '../lib/format.js'

const KIND = {
  fixtures: 'Fixtures & results',
  odds: 'Prices',
  context: 'Match research',
  match_odds: 'Match prices',
}

export function runSummary(run) {
  const cost = run.provider === 'odds_api' ? `${run.credits_used} credit${run.credits_used === 1 ? '' : 's'}` : `${run.requests_made} request${run.requests_made === 1 ? '' : 's'}`
  if (run.status === 'running') return `Working… ${run.progress} of ${run.total}`
  const what =
    run.kind === 'fixtures' ? `${run.items} fixtures saved` :
    run.kind === 'odds' ? `${run.items} matches priced` :
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
