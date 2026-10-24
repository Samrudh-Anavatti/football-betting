import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AiPanel, { PublicAi } from '../components/AiPanel.jsx'
import MarketBoard from '../components/MarketBoard.jsx'
import PickForm from '../components/PickForm.jsx'
import PitchCard from '../components/PitchCard.jsx'
import RunStatus from '../components/RunStatus.jsx'
import TipCard from '../components/TipCard.jsx'
import { Empty, ErrorNote, FormStrip, Freshness, LeagueBadge, Loading, TeamName } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { useRun } from '../hooks/useRun.js'
import { api } from '../lib/api.js'
import { dayLabel, kickoffTime, shortDate } from '../lib/format.js'
import { useAuth } from '../lib/auth.jsx'

const LIVE = new Set(['1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE', 'INT'])

// The match as a scoreboard: league and kick-off above, teams either side of the score.
function Header({ fx }) {
  const played = fx.home_goals != null
  return (
    <section className="relative overflow-hidden -mx-4 sm:mx-0 sm:rounded-2xl bg-ink text-white px-5 sm:px-8 pt-5 pb-7">
      <p className="text-sm text-white/60 flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="inline-flex items-center gap-1.5 text-white/85 font-medium">
          <span className="grid h-5 w-5 place-items-center rounded-[4px] bg-white">
            <LeagueBadge league={fx.league} className="h-3.5 w-3.5" />
          </span>
          {fx.league.name}
          {fx.round ? `, ${fx.round.replace('Regular Season - ', 'matchday ')}` : ''}
        </span>
        <span className="num">
          {dayLabel(fx.kickoff)}, {kickoffTime(fx.kickoff)}
        </span>
        {fx.venue && <span>{fx.venue}</span>}
      </p>
      <div className="mt-6 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 sm:gap-6">
        <Crest team={fx.home} align="right" />
        {played ? (
          <span className="num wide rounded-lg bg-white/[0.08] px-3 sm:px-5 py-1.5 text-3xl sm:text-6xl font-black tracking-tight text-amber">
            {fx.home_goals}–{fx.away_goals}
          </span>
        ) : (
          <span className="num text-xl sm:text-2xl font-bold text-white/40 px-2">v</span>
        )}
        <Crest team={fx.away} />
      </div>
      {fx.status !== 'NS' && (
        <p className={`mt-3 flex items-center justify-center gap-1.5 text-sm ${LIVE.has(fx.status) ? 'text-white font-semibold' : 'text-white/60'}`}>
          {LIVE.has(fx.status) && <span className="h-2 w-2 rounded-full bg-red animate-live" aria-hidden />}
          {fx.status_long}
        </p>
      )}
    </section>
  )
}

// A team's crest on a white disc with its name, stacked on small screens.
function Crest({ team, align = 'left' }) {
  const right = align === 'right'
  return (
    <div className={`flex min-w-0 flex-col sm:flex-row items-center gap-2 sm:gap-4 ${right ? 'sm:flex-row-reverse sm:text-right' : ''} text-center`}>
      <span className="grid h-12 w-12 sm:h-16 sm:w-16 shrink-0 place-items-center rounded-full bg-white shadow-[inset_0_-3px_0_rgba(15,31,54,0.12)]">
        {team.logo ? <img src={team.logo} alt="" className="h-8 w-8 sm:h-11 sm:w-11 object-contain" /> : null}
      </span>
      <span className="font-display text-lg sm:text-[2.4rem] font-extrabold leading-[1.05] tracking-tight [font-stretch:110%] min-w-0 break-words">
        {team.name}
      </span>
    </div>
  )
}

// Signed-in only: the buttons that spend API-Football quota for this match.
function ResearchBar({ fx, data, reload }) {
  const ctx = useRun(() => reload())
  const prices = useRun(() => reload())
  const lineups = useRun(() => reload())
  return (
    <section className="panel px-5 py-4 grid gap-4 sm:grid-cols-3 bg-amber-light/60 shadow-none ring-1 ring-inset ring-amber/50">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn-primary" disabled={ctx.busy} onClick={() => ctx.start(() => api.refreshContext(fx.id))}>
            {ctx.busy ? 'Fetching…' : 'Refresh research'}
          </button>
          <Freshness at={data.context.fetched_at} warnAfter={24} staleAfter={72} />
        </div>
        <p className="text-sm text-ink-soft">
          Form, head-to-head, injuries, season stats, API-Football's prediction and each team's last XI. Uses 8 to 11 requests.
        </p>
        <RunStatus run={ctx.run} error={ctx.error} />
      </div>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn-primary" disabled={prices.busy} onClick={() => prices.start(() => api.refreshMatchMarkets(fx.id))}>
            {prices.busy ? 'Fetching…' : 'Refresh prices'}
          </button>
          <Freshness at={data.odds.pulled_at} warnAfter={6} staleAfter={24} />
        </div>
        <p className="text-sm text-ink-soft">Every market from our bookmakers. Uses 1 request.</p>
        <RunStatus run={prices.run} error={prices.error} />
      </div>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn-primary" disabled={lineups.busy} onClick={() => lineups.start(() => api.refreshLineups(fx.id))}>
            {lineups.busy ? 'Fetching…' : 'Line-ups'}
          </button>
          <Freshness at={data.context.lineups_fetched_at} warnAfter={1} staleAfter={3} prefix="Checked" />
        </div>
        <p className="text-sm text-ink-soft">Confirmed XIs, out 20 to 40 minutes before kick-off. Uses 1 request.</p>
        <RunStatus run={lineups.run} error={lineups.error} />
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

function Prediction({ p, fx }) {
  if (!p) return null
  const pc = p.percent || {}
  return (
    <div className="panel p-4 space-y-2">
      <h3 className="text-lg">API-Football's prediction</h3>
      {p.advice && <p className="text-sm">{p.advice}</p>}
      <div className="grid grid-cols-3 text-center text-sm">
        {[[fx.home.name, pc.home], ['Draw', pc.draw], [fx.away.name, pc.away]].map(([label, v]) => (
          <div key={label}>
            <p className="num text-2xl font-semibold">{v || '–'}</p>
            <p className="text-ink-soft truncate">{label}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function TeamStats({ fx, home, away }) {
  if (!home && !away) return null
  // Home team's record at home, away team's record away: the splits that matter here.
  const rows = [
    ['Played', (s, k) => s?.played?.[k]],
    ['Won, drawn, lost', (s, k) => (s?.wins ? `${s.wins[k]}-${s.draws[k]}-${s.losses[k]}` : null)],
    ['Goals for per game', (s, k) => s?.goals_for_avg?.[k]],
    ['Goals against per game', (s, k) => s?.goals_against_avg?.[k]],
    ['Clean sheets', (s, k) => s?.clean_sheets?.[k]],
    ['Failed to score', (s, k) => s?.failed_to_score?.[k]],
  ]
  return (
    <div className="panel p-4">
      <h3 className="text-lg mb-1">Season so far</h3>
      <p className="text-sm text-ink-soft mb-2">{fx.home.name} at home, {fx.away.name} away, in this competition.</p>
      <table className="w-full text-sm">
        <thead className="text-ink-soft">
          <tr>
            <th />
            <th className="font-medium text-right truncate max-w-[7rem]">{fx.home.name}</th>
            <th className="font-medium text-right truncate max-w-[7rem]">{fx.away.name}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ink/5">
          {rows.map(([label, get]) => (
            <tr key={label}>
              <td className="py-1">{label}</td>
              <td className="text-right num text-base">{get(home, 'home') ?? '–'}</td>
              <td className="text-right num text-base">{get(away, 'away') ?? '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
      <Link to="/fixtures" className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-soft hover:text-ink transition-colors">
        <span aria-hidden>‹</span> Back to fixtures
      </Link>
      <Header fx={fx} />
      {user && <ResearchBar fx={fx} data={data} reload={reload} />}
      {user && <AiPanel fx={fx} board={data.odds} onPick={canPick ? setPick : null} />}

      {data.tips.length > 0 && (
        <section>
          <h2 className="text-2xl mb-3">Our team's pick{data.tips.length > 1 ? 's' : ''}</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {data.tips.map((t) => (
              <TipCard key={t.id} tip={{ ...t, fixture: fx }} />
            ))}
          </div>
        </section>
      )}
      {!user && <PublicAi ai={data.ai} fx={fx} board={data.odds} />}

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <section className="space-y-3 min-w-0">
          <div className="flex flex-wrap items-baseline gap-3">
            <h2 className="text-2xl">Prices</h2>
            <Freshness at={data.odds.pulled_at} warnAfter={6} staleAfter={24} />
          </div>
          {canPick && data.odds.markets.length > 0 && (
            <p className="text-sm text-ink-soft">Click any price to publish it as a tip or log it as a bet.</p>
          )}
          {saved && <p className="text-sm text-pitch font-semibold">{saved === 'tip' ? 'Tip published.' : 'Bet logged to your account.'}</p>}
          {data.odds.markets.length ? (
            <MarketBoard board={data.odds} fx={fx} onPick={canPick ? setPick : null} />
          ) : (
            <Empty title="No prices yet">
              {user ? 'Use Refresh prices above, or pull a whole league from the admin page.' : 'Prices appear closer to kick-off.'}
            </Empty>
          )}
        </section>

        <section className="space-y-4 min-w-0">
          <div className="flex flex-wrap items-baseline gap-3">
            <h2 className="text-2xl">Research</h2>
            <Freshness at={ctx.fetched_at} warnAfter={24} staleAfter={72} />
          </div>
          {(data.pitch?.home.start_xi?.length > 0 || data.pitch?.away.start_xi?.length > 0) && (
            <PitchCard pitch={data.pitch} fx={fx} injuries={ctx.injuries} />
          )}
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
              <Prediction p={ctx.prediction} fx={fx} />
              <TeamStats fx={fx} home={ctx.home_stats} away={ctx.away_stats} />
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
