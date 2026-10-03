import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import OddsBoard from '../components/OddsBoard.jsx'
import PickForm from '../components/PickForm.jsx'
import RunStatus from '../components/RunStatus.jsx'
import TipCard from '../components/TipCard.jsx'
import { Empty, ErrorNote, FormStrip, Freshness, LeagueBadge, Loading, TeamName } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { useRun } from '../hooks/useRun.js'
import { api } from '../lib/api.js'
import { dayLabel, kickoffTime, shortDate } from '../lib/format.js'
import { useAuth } from '../lib/auth.jsx'

function Header({ fx }) {
  const played = fx.home_goals != null
  return (
    <section className="panel px-5 py-5">
      <p className="text-sm text-ink-soft flex flex-wrap items-center gap-x-3">
        <span className="inline-flex items-center gap-1.5">
          <LeagueBadge league={fx.league} />
          {fx.league.name}
          {fx.round ? `, ${fx.round.replace('Regular Season - ', 'matchday ')}` : ''}
        </span>
        <span>
          {dayLabel(fx.kickoff)}, {kickoffTime(fx.kickoff)}
        </span>
        {fx.venue && <span>{fx.venue}</span>}
      </p>
      <div className="mt-3 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 sm:gap-4">
        <TeamName team={fx.home} align="right" className="font-display text-xl sm:text-4xl font-semibold" />
        <span className="num text-3xl sm:text-5xl font-bold">{played ? `${fx.home_goals}–${fx.away_goals}` : 'v'}</span>
        <TeamName team={fx.away} className="font-display text-xl sm:text-4xl font-semibold" />
      </div>
      {fx.status !== 'NS' && <p className="text-center text-sm text-ink-soft mt-1">{fx.status_long}</p>}
    </section>
  )
}

// Signed-in only: the two buttons that spend API quota for this match.
function ResearchBar({ fx, data, reload }) {
  const ctx = useRun(() => reload())
  const prices = useRun(() => reload())
  return (
    <section className="panel px-5 py-4 grid gap-4 sm:grid-cols-2 border-amber/60 bg-amber-light/40">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn-primary" disabled={ctx.busy} onClick={() => ctx.start(() => api.refreshContext(fx.id))}>
            {ctx.busy ? 'Fetching…' : 'Refresh research'}
          </button>
          <Freshness at={data.context.fetched_at} warnAfter={24} staleAfter={72} />
        </div>
        <p className="text-sm text-ink-soft">Head-to-head, form and injuries. Uses 4–6 API-Football requests.</p>
        <RunStatus run={ctx.run} error={ctx.error} />
      </div>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn-primary" disabled={prices.busy} onClick={() => prices.start(() => api.refreshMatchOdds(fx.id))}>
            {prices.busy ? 'Fetching…' : 'Refresh prices'}
          </button>
          <Freshness at={data.odds.pulled_at} warnAfter={6} staleAfter={24} />
        </div>
        <p className="text-sm text-ink-soft">Match result and total goals from UK bookmakers. Uses 2 Odds API credits.</p>
        <RunStatus run={prices.run} error={prices.error} />
      </div>
    </section>
  )
}

function H2H({ rows }) {
  if (!rows?.length) return <p className="text-sm text-ink-faint">No previous meetings found.</p>
  return (
    <ul className="divide-y divide-ink/5">
      {rows.map((m) => (
        <li key={m.id} className="grid grid-cols-[4.5rem_1fr_auto_1fr] gap-2 items-center py-1.5 text-sm">
          <span className="text-ink-soft">{shortDate(m.date)}</span>
          <span className="text-right truncate">{m.home}</span>
          <span className="num text-base font-semibold px-1">
            {m.hg}–{m.ag}
          </span>
          <span className="truncate">{m.away}</span>
        </li>
      ))}
    </ul>
  )
}

function FormList({ team, rows }) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-2">
        <TeamName team={team} className="font-semibold" />
        <span className="ml-auto">
          <FormStrip form={rows} />
        </span>
      </div>
      {rows?.length > 0 && (
        <ul className="text-sm divide-y divide-ink/5">
          {rows.map((m) => (
            <li key={m.id} className="grid grid-cols-[4.5rem_1.25rem_1fr_auto] gap-2 py-1">
              <span className="text-ink-soft">{shortDate(m.date)}</span>
              <span className="text-ink-faint">{m.venue}</span>
              <span className="truncate">{m.venue === 'H' ? m.away : m.home}</span>
              <span className="num text-base">
                {m.gf}–{m.ga}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Injuries({ list, fx }) {
  if (!list) return null
  const byTeam = (id) => list.filter((i) => i.team_id === id)
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {[fx.home, fx.away].map((t) => (
        <div key={t.id}>
          <p className="font-semibold mb-1">{t.name}</p>
          {byTeam(t.id).length ? (
            <ul className="text-sm space-y-0.5">
              {byTeam(t.id).map((i) => (
                <li key={i.player}>
                  {i.player} <span className="text-ink-soft">({i.reason || i.type})</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-faint">None reported</p>
          )}
        </div>
      ))}
    </div>
  )
}

export default function Match() {
  const { id } = useParams()
  const { user } = useAuth()
  const { data, loading, error, reload } = useApi(() => api.match(id), [id])
  const [pick, setPick] = useState(null)
  const [saved, setSaved] = useState(null)

  if (loading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  const fx = data.fixture
  const ctx = data.context
  const canPick = user && fx.status === 'NS'

  return (
    <div className="space-y-6">
      <Link to="/fixtures" className="text-sm font-semibold text-ink-soft hover:text-ink">
        Back to fixtures
      </Link>
      <Header fx={fx} />
      {user && <ResearchBar fx={fx} data={data} reload={reload} />}

      {data.tips.length > 0 && (
        <section>
          <h2 className="text-2xl mb-3">Ivo's pick{data.tips.length > 1 ? 's' : ''}</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {data.tips.map((t) => (
              <TipCard key={t.id} tip={{ ...t, fixture: fx }} />
            ))}
          </div>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <section className="space-y-3">
          <div className="flex flex-wrap items-baseline gap-3">
            <h2 className="text-2xl">Prices</h2>
            <Freshness at={data.odds.pulled_at} warnAfter={6} staleAfter={24} />
          </div>
          {canPick && data.odds.markets.length > 0 && (
            <p className="text-sm text-ink-soft">Click any price to publish it as a tip or log it as a bet.</p>
          )}
          {saved && <p className="text-sm text-pitch font-semibold">{saved === 'tip' ? 'Tip published.' : 'Bet logged to your account.'}</p>}
          {data.odds.markets.length ? (
            <OddsBoard board={data.odds} fx={fx} onPick={canPick ? setPick : null} />
          ) : (
            <Empty title="No prices yet">
              {user ? 'Use Refresh prices above, or pull a whole league from the admin page.' : 'Prices appear closer to kick-off.'}
            </Empty>
          )}
        </section>

        <section className="space-y-4">
          <div className="flex flex-wrap items-baseline gap-3">
            <h2 className="text-2xl">Research</h2>
            <Freshness at={ctx.fetched_at} warnAfter={24} staleAfter={72} />
          </div>
          {ctx.errors && (
            <ErrorNote>
              Some sections failed to load: {Object.entries(ctx.errors).map(([k, v]) => `${k} (${v})`).join('; ')}
            </ErrorNote>
          )}
          {!ctx.fetched_at ? (
            <Empty title="No research fetched yet">
              {user ? 'Use Refresh research above to pull head-to-head, form and injuries.' : 'Check back closer to kick-off.'}
            </Empty>
          ) : (
            <>
              <div className="panel p-4 space-y-5">
                <h3 className="text-lg">Last five matches</h3>
                <FormList team={fx.home} rows={ctx.home_form} />
                <FormList team={fx.away} rows={ctx.away_form} />
              </div>
              <div className="panel p-4">
                <h3 className="text-lg mb-2">Head to head</h3>
                <H2H rows={ctx.h2h} />
              </div>
              <div className="panel p-4">
                <h3 className="text-lg mb-2">Injuries and suspensions</h3>
                <Injuries list={ctx.injuries} fx={fx} />
              </div>
            </>
          )}
          {data.standings.rows.length > 0 && (
            <div className="panel p-4">
              <h3 className="text-lg mb-2">League position</h3>
              <table className="w-full text-sm">
                <thead className="text-ink-soft">
                  <tr>
                    <th className="text-left font-medium py-1">Pos</th>
                    <th className="text-left font-medium">Team</th>
                    <th className="font-medium">P</th>
                    <th className="font-medium">GD</th>
                    <th className="font-medium">Pts</th>
                  </tr>
                </thead>
                <tbody>
                  {data.standings.rows.map((r) => (
                    <tr key={r.team_id} className="text-center">
                      <td className="text-left num text-base py-1">{r.rank}</td>
                      <td className="text-left">{r.team}</td>
                      <td className="num text-base">{r.played}</td>
                      <td className="num text-base">{r.gd > 0 ? `+${r.gd}` : r.gd}</td>
                      <td className="num text-base font-semibold">{r.points}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {pick && (
        <PickForm
          pick={pick}
          fx={fx}
          onClose={() => setPick(null)}
          onSaved={(kind) => {
            setPick(null)
            setSaved(kind)
            reload()
          }}
        />
      )}
    </div>
  )
}
