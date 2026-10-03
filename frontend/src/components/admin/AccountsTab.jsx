import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi.js'
import { api } from '../../lib/api.js'
import { useAuth } from '../../lib/auth.jsx'
import { money, odds, pct, pickLabel, shortDate } from '../../lib/format.js'
import { Empty, ErrorNote, Loading } from '../ui.jsx'

function AccountCard({ a, mine, onSaved }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(a.starting_bankroll)
  const save = async () => {
    await api.setBankroll(Number(value))
    setEditing(false)
    onSaved()
  }
  return (
    <section className="panel overflow-hidden">
      <header className="bg-ink text-white px-5 py-4">
        <p className="text-white/60 text-sm">{a.display_name}'s account</p>
        <p className="num text-4xl font-bold">{money(a.balance)}</p>
        <p className={`num text-lg ${a.profit >= 0 ? 'text-amber' : 'text-red'}`}>
          {a.profit >= 0 ? '+' : ''}
          {money(a.profit)} profit, {pct(a.roi)} return on stake
        </p>
      </header>
      <dl className="grid grid-cols-3 px-5 py-3 text-sm">
        <div>
          <dt className="text-ink-soft">Won / lost</dt>
          <dd className="num text-xl">{a.won}–{a.lost}</dd>
        </div>
        <div>
          <dt className="text-ink-soft">Open bets</dt>
          <dd className="num text-xl">{a.open_bets}</dd>
        </div>
        <div>
          <dt className="text-ink-soft">Money at stake</dt>
          <dd className="num text-xl">{money(a.exposure)}</dd>
        </div>
      </dl>
      <div className="px-5 pb-4 text-sm text-ink-soft flex flex-wrap items-center gap-2">
        Started with {money(a.starting_bankroll)}.
        {mine && !editing && (
          <button type="button" className="font-semibold text-ink underline underline-offset-4" onClick={() => setEditing(true)}>
            Change starting balance
          </button>
        )}
        {editing && (
          <span className="flex gap-2 items-center">
            <input className="input w-28 py-1 num" type="number" min="1" value={value} onChange={(e) => setValue(e.target.value)} />
            <button type="button" className="btn-primary py-1" onClick={save}>Save</button>
          </span>
        )}
      </div>
    </section>
  )
}

export default function AccountsTab() {
  const { user } = useAuth()
  const { data, loading, error, reload } = useApi(() => api.accounts(), [])
  if (loading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />

  const remove = async (id) => {
    if (!confirm('Delete this bet?')) return
    try {
      await api.deleteBet(id)
      reload()
    } catch (e) {
      alert(e.message)
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        {data.accounts.map((a) => (
          <AccountCard key={a.user_id} a={a} mine={a.user_id === user.id} onSaved={reload} />
        ))}
      </div>
      <p className="text-sm text-ink-soft">
        Virtual money only. Log a bet by clicking a price on any upcoming match. Bets settle with the match result.
      </p>
      {data.bets.length === 0 ? (
        <Empty title="No bets logged yet" />
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-ink-soft">
              <tr>
                <th className="px-4 py-2 font-medium">Who</th>
                <th className="py-2 font-medium">Match</th>
                <th className="py-2 font-medium">Bet</th>
                <th className="py-2 font-medium text-right">Odds</th>
                <th className="py-2 font-medium text-right">Stake</th>
                <th className="py-2 px-3 font-medium text-right">Return</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-ink/5">
              {data.bets.map((b) => (
                <tr key={b.id}>
                  <td className="px-4 py-2 font-medium">{b.user}</td>
                  <td className="py-2 pr-3">
                    <Link to={`/match/${b.fixture.id}`} className="hover:underline">
                      {b.fixture.home.name} v {b.fixture.away.name}
                    </Link>
                    <div className="text-ink-faint">{shortDate(b.fixture.kickoff)}</div>
                  </td>
                  <td className="py-2 pr-3">{pickLabel(b, b.fixture)}</td>
                  <td className="py-2 text-right num text-base">{odds(b.odds)}</td>
                  <td className="py-2 text-right num text-base">{money(b.stake)}</td>
                  <td className={`py-2 px-3 text-right num text-base ${b.status === 'won' ? 'text-pitch' : b.status === 'lost' ? 'text-red' : 'text-ink-soft'}`}>
                    {b.status === 'pending' ? 'Open' : money(b.profit)}
                  </td>
                  <td className="py-2 pr-4 text-right">
                    {b.user_id === user.id && b.status === 'pending' && new Date(b.fixture.kickoff) > new Date() && (
                      <button type="button" className="text-red font-semibold" onClick={() => remove(b.id)}>
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
