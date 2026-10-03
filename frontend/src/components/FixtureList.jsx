import { Link } from 'react-router-dom'
import { dayLabel, groupBy, kickoffTime } from '../lib/format.js'
import { LeagueBadge, Price, TeamName } from './ui.jsx'

const LIVE = new Set(['1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE', 'INT'])

function Row({ fx, results }) {
  const live = LIVE.has(fx.status)
  const showScore = results || live
  return (
    <Link
      to={`/match/${fx.id}`}
      className="grid grid-cols-[3rem_minmax(0,1fr)_auto] sm:grid-cols-[3.5rem_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 hover:bg-chalk/70"
    >
      <span className={`num text-base ${live ? 'text-red font-semibold' : 'text-ink-soft'}`}>
        {live ? fx.status : results ? 'FT' : kickoffTime(fx.kickoff)}
      </span>
      <span className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 min-w-0 font-medium">
        <TeamName team={fx.home} align="right" />
        <span className="num text-lg font-semibold w-10 sm:w-12 text-center">
          {showScore && fx.home_goals != null ? `${fx.home_goals}–${fx.away_goals}` : 'v'}
        </span>
        <TeamName team={fx.away} />
      </span>
      <span className="hidden sm:flex gap-1">
        {!results &&
          (fx.best_1x2 ? (
            ['home', 'draw', 'away'].map((s) => <Price key={s} value={fx.best_1x2[s]} />)
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
          <h3 className="text-lg text-ink-soft mb-2">{dayLabel(day.items[0].kickoff)}</h3>
          <div className="space-y-3">
            {groupBy(day.items, (f) => f.league.id).map((lg) => (
              <div key={lg.key} className="panel overflow-hidden">
                <div className="flex items-center gap-2 px-4 py-2 bg-ink/[0.03] border-b border-ink/10 text-sm font-semibold">
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
                <div className="divide-y divide-ink/5">
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
