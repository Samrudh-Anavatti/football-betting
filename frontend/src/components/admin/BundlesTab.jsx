import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi.js'
import { api } from '../../lib/api.js'
import { dayLabel, kickoffTime, money, odds, pickLabel } from '../../lib/format.js'
import { combinedOdds, stakeFor } from '../../lib/staking.js'
import { Empty, ErrorNote, Loading, Price } from '../ui.jsx'

function PlanSettings({ plan, onSaved }) {
  const [form, setForm] = useState({ base_stake: plan.base_stake, target_odds: plan.target_odds, bank: plan.bank })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const save = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onSaved(await api.updateStakingPlan(Object.fromEntries(Object.entries(form).map(([k, v]) => [k, Number(v)]))))
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={save} className="panel p-4 space-y-3">
      <h2 className="text-xl">Plan</h2>
      <div className="grid grid-cols-3 gap-3">
        <label>
          <span className="label">Base stake (£)</span>
          <input className="input num" type="number" min="0.5" step="0.5" value={form.base_stake} onChange={set('base_stake')} required />
        </label>
        <label>
          <span className="label">Target odds</span>
          <input className="input num" type="number" min="1.5" step="0.1" value={form.target_odds} onChange={set('target_odds')} required />
        </label>
        <label>
          <span className="label">Bank (£)</span>
          <input className="input num" type="number" min="1" step="1" value={form.bank} onChange={set('bank')} required />
        </label>
      </div>
      <p className="text-sm text-ink-soft">
        Each run aims to make {money(plan.target_profit)}. After a loss the stake goes up about ×{plan.multiplier.toFixed(2)}.
        The bank covers {plan.survivable_losses} losses in a row. Changes apply from the next bundle.
      </p>
      <ErrorNote error={error} />
      <button className="btn-primary" disabled={busy}>
        {busy ? 'Saving…' : 'Save plan'}
      </button>
    </form>
  )
}

// Pick open picks into the next bundle: combined odds and the exact stake update as you go.
function Builder({ state, tips, onCreated }) {
  const { plan, run } = state
  const [chosen, setChosen] = useState([])
  const [stake, setStake] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const picked = tips.filter((t) => chosen.includes(t.id))
  const total = combinedOdds(picked)
  const exact = picked.length && total >= 1.5 ? stakeFor(plan, run.losses, total) : null
  const toggle = (t) => {
    setChosen(chosen.includes(t.id) ? chosen.filter((i) => i !== t.id) : [...chosen, t.id])
    setStake('')
  }
  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      await onCreated({ tip_ids: chosen, stake: stake ? Number(stake) : null })
      setChosen([])
      setStake('')
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  if (tips.length === 0)
    return <Empty title="No open picks to bundle">Make today's picks first, then come back to bundle them.</Empty>

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_18rem] items-start">
      <ul className="panel divide-y divide-ink/5">
        {tips.map((t) => {
          const on = chosen.includes(t.id)
          const clash = !on && picked.some((p) => p.fixture_id === t.fixture_id)
          return (
            <li key={t.id}>
              <label className={`flex items-center gap-3 px-4 py-2.5 ${clash ? 'opacity-40' : 'cursor-pointer hover:bg-ink/[0.03]'}`}>
                <input type="checkbox" className="h-4 w-4 accent-ink" checked={on} disabled={clash} onChange={() => toggle(t)} />
                <div className="min-w-0 flex-1">
                  <p className="font-semibold truncate">{pickLabel(t, t.fixture)}</p>
                  <p className="text-sm text-ink-soft truncate">
                    {t.fixture.home.name} v {t.fixture.away.name} · {dayLabel(t.fixture.kickoff)}, {kickoffTime(t.fixture.kickoff)}
                  </p>
                </div>
                <Price value={t.odds} board={on} />
              </label>
            </li>
          )
        })}
      </ul>
      <div className="panel p-4 space-y-3 lg:sticky lg:top-4">
        <p className="text-sm text-ink-soft">
          Run {run.number}, bet {run.step}
          {run.losses > 0 && <>, recovering {money(run.losses)}</>}
        </p>
        <div className="flex items-end justify-between">
          <div>
            <p className="text-sm text-ink-soft">
              {picked.length} pick{picked.length === 1 ? '' : 's'}
            </p>
            <Price value={picked.length ? total : null} board />
          </div>
          <div className="text-right">
            <p className="text-sm text-ink-soft">Exact stake</p>
            <p className="num text-2xl font-bold">{exact == null ? '–' : money(exact)}</p>
          </div>
        </div>
        {picked.length > 0 && total < plan.target_odds * 0.85 && (
          <p className="text-sm text-amber-dark">Below the {odds(plan.target_odds)} target: add another pick?</p>
        )}
        <label className="block">
          <span className="label">Stake placed, if different (£)</span>
          <input className="input num" type="number" min="0.1" step="0.01" placeholder={exact == null ? '' : exact.toFixed(2)} value={stake} onChange={(e) => setStake(e.target.value)} />
        </label>
        <ErrorNote error={error} />
        <button type="button" className="btn-primary w-full" disabled={busy || exact == null} onClick={create}>
          {busy ? 'Creating…' : 'Create bundle'}
        </button>
      </div>
    </div>
  )
}

export default function BundlesTab() {
  const state = useApi(() => api.staking(), [])
  const tips = useApi(() => api.adminTips(), [])
  if ((state.loading && !state.data) || (tips.loading && !tips.data)) return <Loading />
  if (state.error || tips.error) return <ErrorNote error={state.error || tips.error} />

  const s = state.data
  // A pick can be in one bundle only; a lost bundle can still have picks waiting to be played.
  const bundled = new Set([s.current, ...s.history].filter(Boolean).flatMap((b) => b.legs.map((l) => l.tip_id)))
  const open = tips.data.tips
    .filter((t) => t.published && t.status === 'pending' && !t.locked && !bundled.has(t.id))
    .sort((a, b) => a.fixture.kickoff.localeCompare(b.fixture.kickoff))

  const create = async (body) => {
    await api.createBundle(body)
    state.reload()
  }
  const remove = async () => {
    if (!confirm('Delete this bundle? Only for one made by mistake.')) return
    try {
      await api.deleteBundle(s.current.id)
      state.reload()
    } catch (e) {
      alert(e.message)
    }
  }

  return (
    <div className="space-y-6">
      {s.current ? (
        <div className="panel p-4 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-xl">
              Live bundle: run {s.current.run}, bet {s.current.step}
            </h2>
            <span className="num">
              {odds(s.current.odds)} · {money(s.current.stake)} to return {money(s.current.returns)}
            </span>
            <Link to="/staking" className="link text-sm sm:ml-auto">
              See the page
            </Link>
            <button type="button" className="btn-ghost text-red" onClick={remove}>
              Delete
            </button>
          </div>
          <ul className="text-sm space-y-1">
            {s.current.legs.map((l) => (
              <li key={l.tip_id}>
                {pickLabel(l.tip, l.tip.fixture)} <span className="text-ink-soft">({l.tip.fixture.home.name} v {l.tip.fixture.away.name})</span>{' '}
                <span className="num">{odds(l.odds)}</span> <span className="text-ink-soft capitalize">{l.tip.status}</span>
              </li>
            ))}
          </ul>
          <p className="text-sm text-ink-soft">The next bundle can be made once this one settles: its result sets the next stake.</p>
        </div>
      ) : (
        <Builder state={s} tips={open} onCreated={create} />
      )}
      <PlanSettings key={JSON.stringify(s.plan)} plan={s.plan} onSaved={state.setData} />
    </div>
  )
}
