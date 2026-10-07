import { useState } from 'react'
import { api } from '../lib/api.js'
import { odds as fmtOdds, pickLabel } from '../lib/format.js'
import { ErrorNote } from './ui.jsx'

// Slide-over form opened by clicking a price on the market board (or "Use this"
// on an AI suggestion, which pre-fills stake, confidence and reasoning). One
// selection, two outcomes: publish it as a tip, or log it as a virtual bet.
export default function PickForm({ pick, fx, onClose, onSaved }) {
  const [form, setForm] = useState({
    odds: pick.odds,
    bookmaker: pick.bookmaker,
    stake_units: pick.prefill?.stake_units ?? 1,
    confidence: pick.prefill?.confidence ?? 3,
    reasoning: pick.prefill?.reasoning ?? '',
    stake: 10,
  })
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const base = {
    fixture_id: fx.id,
    market_id: pick.market_id ?? null,
    market: pick.market,
    selection: pick.selection,
    line: pick.line ?? null,
  }
  const submit = async (kind) => {
    setBusy(kind)
    setError(null)
    try {
      if (kind === 'tip') {
        await api.createTip({
          ...base,
          odds: Number(form.odds),
          bookmaker: form.bookmaker,
          stake_units: Number(form.stake_units),
          confidence: Number(form.confidence),
          reasoning: form.reasoning || null,
        })
      } else {
        await api.createBet({ ...base, odds: Number(form.odds), bookmaker: form.bookmaker, stake: Number(form.stake) })
      }
      onSaved(kind)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="fixed inset-0 z-30 flex justify-end" role="dialog" aria-modal="true" aria-label="New pick">
      <button type="button" aria-label="Close" className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white h-full overflow-y-auto shadow-xl">
        <div className="bg-ink text-white px-5 py-4">
          <p className="text-sm text-white/60">
            {fx.home.name} v {fx.away.name}
          </p>
          <p className="font-display text-3xl font-semibold">{pickLabel(pick, fx)}</p>
          <p className="text-amber num text-xl">
            {fmtOdds(pick.odds)} at {pick.bookmaker}
          </p>
        </div>
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <label>
              <span className="label">Odds taken</span>
              <input className="input num" type="number" step="0.01" min="1.01" value={form.odds} onChange={set('odds')} />
            </label>
            <label>
              <span className="label">Bookmaker</span>
              <input className="input" value={form.bookmaker || ''} onChange={set('bookmaker')} />
            </label>
          </div>

          <fieldset className="rounded-md border border-ink/10 p-4 space-y-3">
            <legend className="px-1 font-display text-lg font-semibold">Publish as a tip</legend>
            <div className="grid grid-cols-2 gap-3">
              <label>
                <span className="label">Stake (units)</span>
                <input className="input num" type="number" step="0.5" min="0.5" max="10" value={form.stake_units} onChange={set('stake_units')} />
              </label>
              <label>
                <span className="label">Confidence, 1 to 5</span>
                <input className="input num" type="number" min="1" max="5" value={form.confidence} onChange={set('confidence')} />
              </label>
            </div>
            <label className="block">
              <span className="label">Reasoning (shown publicly)</span>
              <textarea
                className="input min-h-[7rem]"
                value={form.reasoning}
                onChange={set('reasoning')}
                placeholder="Why this price is wrong: form, injuries, matchup…"
              />
            </label>
            <button type="button" className="btn-primary w-full" disabled={!!busy} onClick={() => submit('tip')}>
              {busy === 'tip' ? 'Publishing…' : 'Publish tip'}
            </button>
          </fieldset>

          <fieldset className="rounded-md border border-ink/10 p-4 space-y-3">
            <legend className="px-1 font-display text-lg font-semibold">Log a virtual bet</legend>
            <label className="block">
              <span className="label">Stake (£, from your tracked account)</span>
              <input className="input num" type="number" step="1" min="1" value={form.stake} onChange={set('stake')} />
            </label>
            <button type="button" className="btn-ghost w-full" disabled={!!busy} onClick={() => submit('bet')}>
              {busy === 'bet' ? 'Logging…' : 'Log bet'}
            </button>
          </fieldset>

          <ErrorNote error={error} />
          <button type="button" className="btn-ghost w-full" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
