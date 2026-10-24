import { useEffect, useState } from 'react'
import { useApi } from '../../hooks/useApi.js'
import { api } from '../../lib/api.js'
import { ago } from '../../lib/format.js'
import { runSummary } from '../RunStatus.jsx'
import { ErrorNote, Loading } from '../ui.jsx'

const STATUS_DOT = { ok: 'bg-pitch', partial: 'bg-amber', error: 'bg-red', running: 'bg-ink/40' }

function LastRun({ run }) {
  if (!run) return <span className="text-ink-faint">Not run yet</span>
  return (
    <span className="inline-flex items-start gap-1.5" title={run.message || undefined}>
      <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[run.status]}`} aria-hidden />
      <span>
        {ago(run.started_at)}
        <span className="block text-ink-faint">{runSummary(run)}</span>
        {run.message && run.status !== 'ok' && <span className="block text-red">{run.message}</span>}
      </span>
    </span>
  )
}

// The background refresh schedule: on/off, the credit reserve, and what each job did today.
export default function ScheduleCard({ provider }) {
  const { data, loading, error, reload, setData } = useApi(() => api.schedule(), [])
  const [reserve, setReserve] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  useEffect(() => {
    const t = setInterval(reload, 60_000)
    return () => clearInterval(t)
  }, [reload])
  useEffect(() => {
    if (data && reserve === '') setReserve(String(data.reserve))
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = async (body) => {
    setSaving(true)
    setSaveError(null)
    try {
      const s = await api.updateSchedule(body)
      setData(s)
      setReserve(String(s.reserve))
    } catch (e) {
      setSaveError(e)
    } finally {
      setSaving(false)
    }
  }

  if (loading && !data) return <section className="panel px-5"><Loading /></section>
  if (error && !data) return <ErrorNote error={error} />

  const state = !data.running ? 'Not running' : data.enabled ? 'On' : 'Paused'
  const tone = state === 'On' ? 'bg-pitch-light text-pitch' : state === 'Paused' ? 'bg-amber-light text-amber-dark' : 'bg-red-light text-red'
  const left = provider.quota.remaining
  const holding = data.enabled && left != null && left <= data.reserve
  const reserveValue = Number(reserve)
  const reserveValid = reserve !== '' && Number.isInteger(reserveValue) && reserveValue >= 0

  return (
    <section className="panel overflow-hidden">
      <header className="px-5 pt-4 pb-3 border-b border-ink/10">
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="text-2xl">Refresh schedule</h3>
          <span className={`rounded px-2 py-0.5 text-xs font-semibold ${tone}`}>{state}</span>
          <button type="button" className="ml-auto btn-ghost" disabled={saving || !data.running} onClick={() => save({ enabled: !data.enabled })}>
            {data.enabled ? 'Pause' : 'Turn on'}
          </button>
        </div>
        <p className="text-sm text-ink-soft mt-0.5 max-w-3xl">
          Keeps scores, prices, research and AI analyses up to date in the background. The buttons below still work for
          anything you want sooner.
          {!data.running && ' The schedule is switched off on the server (SCHEDULER=off).'}
        </p>
      </header>

      <div className="px-5 py-4 grid gap-4 sm:grid-cols-2 border-b border-ink/10">
        <div className="space-y-1.5">
          <p>
            <span className="num text-3xl font-bold">{data.requests_today.toLocaleString()}</span>
            <span className="text-ink-soft"> API-Football requests used by the schedule today (UTC)</span>
          </p>
          <form
            className="flex flex-wrap items-center gap-2 text-sm"
            onSubmit={(e) => {
              e.preventDefault()
              if (reserveValid) save({ reserve: reserveValue })
            }}
          >
            <label htmlFor="reserve" className="text-ink-soft">Stop for the day when this many are left:</label>
            <input
              id="reserve"
              type="number"
              min="0"
              step="100"
              inputMode="numeric"
              className="w-24 rounded-md border border-ink/15 px-2 py-1 num"
              value={reserve}
              onChange={(e) => setReserve(e.target.value)}
            />
            <button type="submit" className="font-semibold underline underline-offset-4 disabled:opacity-50" disabled={saving || !reserveValid || reserveValue === data.reserve}>
              Save
            </button>
          </form>
          {holding && (
            <p className="text-sm text-amber-dark font-semibold">
              At the reserve: only live scores are being fetched until the allowance resets at midnight UTC.
            </p>
          )}
        </div>
        <div className="space-y-1.5">
          <p>
            <span className="num text-3xl font-bold">${data.ai.spent_usd.toFixed(2)}</span>
            <span className="text-ink-soft"> of ${data.ai.limit_usd.toFixed(0)} AI budget spent this month</span>
          </p>
          <p className="text-sm text-ink-soft">
            Scheduled analyses stop at ${data.ai.auto_stops_at_usd.toFixed(2)}, so the rest stays free for the Analyse button.
          </p>
        </div>
        {saveError && <div className="sm:col-span-2"><ErrorNote error={saveError} /></div>}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-ink-soft text-left">
            <tr>
              <th className="px-5 py-2 font-medium">Job</th>
              <th className="py-2 pr-4 font-medium">When</th>
              <th className="py-2 pr-4 font-medium">Last run</th>
              <th className="py-2 pr-5 font-medium text-right">Today</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink/5 align-top">
            {data.jobs.map((j) => (
              <tr key={j.kind}>
                <td className="px-5 py-2 font-semibold whitespace-nowrap">
                  {j.label}
                </td>
                <td className="py-2 pr-4 text-ink-soft min-w-[14rem]">{j.cadence}</td>
                <td className="py-2 pr-4 min-w-[12rem]"><LastRun run={j.last_run} /></td>
                <td className="py-2 pr-5 text-right whitespace-nowrap num">
                  {j.runs_today} run{j.runs_today === 1 ? '' : 's'}
                  {j.kind !== 'analysis' && <span className="block text-ink-faint">{j.requests_today} requests</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
