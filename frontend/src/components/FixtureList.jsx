import { Link } from 'react-router-dom'
import { dayLabel, groupBy, kickoffTime, odds } from '../lib/format.js'
import { LeagueBadge, TeamName } from './ui.jsx'

const LIVE = new Set(['1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE', 'INT'])

function Row({ fx, results }) {
  const live = LIVE.has(fx.status)
  const showScore = results || live
  return (
    <Link
      to={`/match/${fx.id}`}
      className="group grid grid-cols-[3rem_minmax(0,1fr)_auto] sm:grid-cols-[3.75rem_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 transition-colors hover:bg-amber-light/50"
    >
      <span className={`num text-[15px] inline-flex items-center gap-1.5 ${live ? 'text-red font-bold' : 'text-ink-soft'}`}>
        {live && <span className="h-1.5 w-1.5 rounded-full bg-red animate-live" aria-hidden />}
        {live ? fx.status : results ? 'FT' : kickoffTime(fx.kickoff)}
      </span>
      <span className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2.5 min-w-0 font-medium">
        <TeamName team={fx.home} align="right" />
        {showScore && fx.home_goals != null ? (
          <span className={`num text-[15px] font-bold w-12 text-center rounded-[4px] py-0.5 ${live ? 'bg-red text-white' : 'bg-ink text-white'}`}>
            {fx.home_goals}–{fx.away_goals}
          </span>
        ) : (
          <span className="w-12 text-center text-sm text-ink-faint">v</span>
        )}
        <TeamName team={fx.away} />
      </span>
      <span className="hidden sm:flex gap-1">
        {!results &&
          (fx.best_1x2 ? (
            ['home', 'draw', 'away'].map((s) => (
              <span key={s} className="price group-hover:ring-ink/30">
                <span className="text-[17px]">{odds(fx.best_1x2[s])}</span>
              </span>
            ))
          ) : (
            <span className="text-xs text-ink-faint w-[10.5rem] text-right">No prices yet</span>
          ))}
      </span>
    </Link>
  )
}

// Fixtures grouped by day, then by league within the day.
export default function FixtureList({ fixtures, results = false }) {
  const days = groupBy(fixtures, (f) => new Date(f.kickoff).toDateString())
  return (
    <div className="space-y-6">
      {days.map((day) => (
        <section key={day.key}>
          <h3 className="text-lg mb-2.5">{dayLabel(day.items[0].kickoff)}</h3>
          <div className="space-y-3">
            {groupBy(day.items, (f) => f.league.id).map((lg) => (
              <div key={lg.key} className="panel overflow-hidden">
                <div className="flex items-center gap-2 px-4 pt-3 pb-2 border-b border-ink/10 text-sm font-bold">
                  <LeagueBadge league={lg.items[0].league} />
                  {lg.items[0].league.name}
                  {!results && (
                    <span className="ml-auto hidden sm:flex gap-1 text-xs font-medium text-ink-faint">
                      <span className="w-[3.25rem] text-center">1</span>
                      <span className="w-[3.25rem] text-center">X</span>
                      <span className="w-[3.25rem] text-center">2</span>
                    </span>
                  )}
                </div>
                <div className="divide-y divide-ink/[0.06]">
                  {lg.items.map((fx) => (
                    <Row key={fx.id} fx={fx} results={results} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
