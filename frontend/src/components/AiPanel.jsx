import { Fragment, useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi.js'
import { useRun } from '../hooks/useRun.js'
import { api } from '../lib/api.js'
import { ago, odds, pct, pickLabel, teamify } from '../lib/format.js'
import RunStatus from './RunStatus.jsx'
import { ErrorNote, Loading } from './ui.jsx'

// Signed-in only. Claude reads this match's bundle (prices, research, table)
// and records an analysis; follow-up questions continue the same conversation.
// Suggestions are private: "Use this" opens the normal pick form, so anything
// published is Ivo's call.

const usd = (x) => (x == null ? '–' : `$${x < 0.1 ? x.toFixed(3) : x.toFixed(2)}`)

// Just enough Markdown for Claude's replies: paragraphs, bullets, **bold**.
function inline(text) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') ? <strong key={i}>{part.slice(2, -2)}</strong> : <Fragment key={i}>{part}</Fragment>,
  )
}

function Prose({ text }) {
  const blocks = text.split(/\n{2,}/)
  return (
    <div className="space-y-2 text-[15px] leading-relaxed">
      {blocks.map((b, i) => {
        const lines = b.split('\n')
        if (lines.every((l) => /^\s*[-*] /.test(l))) {
          return (
            <ul key={i} className="list-disc pl-5 space-y-1">
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*[-*] /, ''))}</li>
              ))}
            </ul>
          )
        }
        const heading = /^#{1,4} /.test(b)
        return (
          <p key={i} className={heading ? 'font-semibold' : ''}>
            {lines.map((l, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {inline(l.replace(/^#{1,4} /, ''))}
              </Fragment>
            ))}
          </p>
        )
      })}
    </div>
  )
}

const PROB_ROWS = [
  ['home_win', (fx) => `${fx.home.name} win`, (m) => m?.result?.home],
  ['draw', () => 'Draw', (m) => m?.result?.draw],
  ['away_win', (fx) => `${fx.away.name} win`, (m) => m?.result?.away],
  ['over_2_5_goals', () => 'Over 2.5 goals', (m) => m?.over_2_5],
  ['both_teams_score', () => 'Both teams score', (m) => m?.btts_yes],
]

function findOnBoard(board, marketId, value) {
  const m = board?.markets?.find((x) => x.id === marketId)
  for (const g of m?.groups || []) for (const s of g.selections) if (s.value === value) return { market: m, sel: s }
  return null
}

function Prediction({ pred, fx, board, tips, onPick }) {
  const a = pred.analysis
  const tracked = tips.filter((t) => pred.tips.includes(t.id))
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded px-2 py-0.5 text-sm font-semibold ${a.no_bet ? 'bg-ink/10' : 'bg-pitch text-white'}`}>
          {a.no_bet ? 'No bet' : `${a.suggested_bets.length} suggested bet${a.suggested_bets.length === 1 ? '' : 's'}`}
        </span>
        <span className="text-sm text-ink-soft">Analysis #{pred.id}, {ago(pred.created_at)}</span>
      </div>
      <p className="text-[15px] leading-relaxed">{a.summary}</p>

      <table className="w-full text-sm">
        <thead className="text-ink-soft">
          <tr>
            <th className="text-left font-medium py-1">Chance of</th>
            <th className="font-medium text-right">Claude</th>
            <th className="font-medium text-right" title="Bookmakers' consensus with the margin removed, when Claude ran">
              Market
            </th>
            <th className="font-medium text-right">Gap</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ink/5">
          {PROB_ROWS.map(([key, label, mk]) => {
            const c = a.probabilities[key]
            const m = mk(pred.market_probs)
            const gap = c != null && m != null ? c - m : null
            return (
              <tr key={key}>
                <td className="py-1">{label(fx)}</td>
                <td className="text-right num text-base">{pct(c, 0)}</td>
                <td className="text-right num text-base text-ink-soft">{pct(m, 0)}</td>
                <td className={`text-right num text-base ${gap > 0.03 ? 'text-pitch' : gap < -0.03 ? 'text-red' : 'text-ink-faint'}`}>
                  {gap == null ? '–' : `${gap > 0 ? '+' : ''}${(gap * 100).toFixed(0)}`}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {a.suggested_bets.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-display text-lg font-semibold">Suggested bets</h4>
          {a.suggested_bets.map((b, i) => {
            const found = findOnBoard(board, b.market_id, b.value)
            const now = found?.sel.best
            const ok = now != null && now >= b.min_odds
            return (
              <div key={i} className="rounded-md border border-ink/10 p-3 space-y-1.5">
                <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
                  <p className="font-semibold min-w-0">
                    {teamify(b.market, fx)}: {teamify(b.value, fx)}
                  </p>
                  <p className="ml-auto text-sm text-ink-soft whitespace-nowrap">
                    take {odds(b.min_odds)}+ · {b.stake_units}u · confidence {b.confidence}/5
                  </p>
                </div>
                <p className="text-sm leading-relaxed text-ink/85">{b.reasoning}</p>
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <span className={ok ? 'text-pitch font-semibold' : 'text-ink-soft'}>
                    {now == null ? 'Not on the board now' : `Best now ${odds(now)} at ${found.sel.best_bookmaker}`}
                    {now != null && !ok && ', below Claude’s minimum'}
                  </span>
                  {onPick && found && (
                    <button
                      type="button"
                      className="btn-ghost py-1 ml-auto"
                      onClick={() =>
                        onPick({
                          market_id: found.market.id,
                          market: found.market.name,
                          selection: found.sel.value,
                          line: found.sel.line,
                          odds: found.sel.best,
                          bookmaker: found.sel.best_bookmaker,
                          prefill: { stake_units: b.stake_units, confidence: b.confidence, reasoning: b.reasoning },
                        })
                      }
                    >
                      Use this
                    </button>
                  )}
                </div>
              </div>
            )
          })}
          {tracked.length > 0 && (
            <p className="text-xs text-ink-soft">
              Tracked privately for the AI's record: {tracked.map((t) => `${pickLabel(t, fx)} at ${odds(t.odds)}`).join('; ')}.
            </p>
          )}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 text-sm">
        {a.key_factors.length > 0 && (
          <div>
            <h4 className="font-semibold mb-1">Key factors</h4>
            <ul className="list-disc pl-5 space-y-0.5">{a.key_factors.map((f, i) => <li key={i}>{f}</li>)}</ul>
          </div>
        )}
        {a.data_gaps.length > 0 && (
          <div>
            <h4 className="font-semibold mb-1">What it didn't have</h4>
            <ul className="list-disc pl-5 space-y-0.5 text-ink-soft">{a.data_gaps.map((f, i) => <li key={i}>{f}</li>)}</ul>
          </div>
        )}
      </div>
    </div>
  )
}

function Conversation({ thread, busy, onSend }) {
  const [text, setText] = useState('')
  const send = (e) => {
    e.preventDefault()
    if (!text.trim()) return
    onSend(text.trim())
    setText('')
  }
  return (
    <div className="space-y-3">
      {thread.messages.map((m) =>
        m.role === 'user' ? (
          <div key={m.id} className="ml-auto max-w-[85%] rounded-lg bg-ink text-white px-3 py-2">
            <p className="text-xs text-white/60 mb-0.5">{m.author}</p>
            <p className="text-[15px] whitespace-pre-wrap">{m.text}</p>
          </div>
        ) : (
          <div key={m.id} className="max-w-[95%] space-y-1">
            {m.text && <Prose text={m.text} />}
            {m.prediction_id && <p className="text-xs font-semibold text-pitch">Recorded analysis #{m.prediction_id}</p>}
          </div>
        ),
      )}
      <form onSubmit={send} className="flex gap-2 items-end">
        <textarea
          className="input min-h-[2.75rem] flex-1"
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) send(e)
          }}
          placeholder="Ask a follow-up, or tell it something it doesn't know (team news, a price you've seen)…"
          aria-label="Message Claude"
          disabled={busy}
        />
        <button className="btn-primary" disabled={busy || !text.trim()}>
          {busy ? 'Thinking…' : 'Send'}
        </button>
      </form>
    </div>
  )
}

export default function AiPanel({ fx, board, onPick }) {
  const { data, loading, error, reload } = useApi(() => api.matchAi(fx.id), [fx.id])
  const r = useRun(() => reload())
  const [threadIdx, setThreadIdx] = useState(0)
  useEffect(() => {
    if (data?.running && !r.run) r.resume(data.running)
  }, [data?.running]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading && !data) return <Loading label="Loading Claude's analysis" />
  if (error) return <ErrorNote error={error} />

  const thread = data.threads[threadIdx]
  const latestPred = thread?.predictions[thread.predictions.length - 1]
  const over = data.budget.spent_usd >= data.budget.limit_usd
  const canRun = data.configured && !r.busy && !over && fx.status === 'NS'

  return (
    <section className="panel border-ink/30 overflow-hidden">
      <header className="px-5 py-3 bg-ink text-white flex flex-wrap items-center gap-x-4 gap-y-1">
        <h2 className="text-2xl">Claude's view</h2>
        <span className="text-sm text-white/60">
          {data.model} on {data.provider}
        </span>
        <span className={`sm:ml-auto text-sm ${over ? 'text-amber' : 'text-white/70'}`}>
          {usd(data.budget.spent_usd)} of {usd(data.budget.limit_usd)} used this month
        </span>
      </header>
      <div className="p-5 space-y-5">
        {!data.configured && <ErrorNote>Claude isn't connected yet: add FOUNDRY_RESOURCE and FOUNDRY_API_KEY to the backend's settings.</ErrorNote>}
        {!thread ? (
          <div className="space-y-3">
            <p className="text-ink-soft">
              Claude reads everything on this page (prices across all markets, form, head-to-head, injuries, season stats,
              API-Football's prediction, line-ups if out) and says where it sees value, or that there's none. Its calls
              stay private and are tracked against the market and Ivo. Refresh prices and research first.
            </p>
            <button type="button" className="btn-primary" disabled={!canRun} onClick={() => r.start(() => api.analyse(fx.id))}>
              {r.busy ? 'Claude is analysing…' : `Analyse with Claude (about ${usd(data.estimate_usd)})`}
            </button>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-ink-soft">
              <span>
                Started by {thread.created_by} {ago(thread.created_at)}, data as of {ago(thread.bundle_built_at)}.
                This conversation has cost {usd(thread.cost_usd)}.
              </span>
              <button
                type="button"
                className="btn-ghost py-1 sm:ml-auto"
                disabled={!canRun}
                onClick={() => {
                  setThreadIdx(0)
                  r.start(() => api.analyse(fx.id))
                }}
                title="Starts a new conversation with the latest prices and research"
              >
                Fresh analysis with latest data (about {usd(data.estimate_usd)})
              </button>
            </div>
            {latestPred ? (
              <Prediction pred={latestPred} fx={fx} board={board} tips={data.tips} onPick={fx.status === 'NS' ? onPick : null} />
            ) : (
              !r.busy && <p className="text-sm text-ink-soft">No structured analysis recorded in this conversation.</p>
            )}
            <div className="border-t border-ink/10 pt-4">
              <h3 className="text-lg mb-2">Conversation</h3>
              <Conversation thread={thread} busy={r.busy || !canRun} onSend={(text) => r.start(() => api.chatAi(thread.id, text))} />
            </div>
            {data.threads.length > 1 && (
              <div className="text-sm">
                <span className="text-ink-soft">Earlier conversations: </span>
                {data.threads.map((t, i) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`mr-2 underline underline-offset-4 ${i === threadIdx ? 'font-semibold' : 'text-ink-soft'}`}
                    onClick={() => setThreadIdx(i)}
                  >
                    {i === 0 ? 'latest' : ago(t.created_at)}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
        <RunStatus run={r.run} error={r.error} />
      </div>
    </section>
  )
}
