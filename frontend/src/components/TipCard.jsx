import { Link } from 'react-router-dom'
import { dayLabel, kickoffTime, pickLabel, signed } from '../lib/format.js'
import { LeagueBadge, Price } from './ui.jsx'

const STATUS = {
  won: 'bg-pitch text-white',
  lost: 'bg-red text-white',
  void: 'bg-ink/15 text-ink',
}

// A tip styled like a betting slip: the pick, the price, the stake, Ivo's reasoning.
export default function TipCard({ tip }) {
  const fx = tip.fixture
  return (
    <article className="panel overflow-hidden flex flex-col">
      <Link to={`/match/${fx.id}`} className="px-4 pt-3 pb-2 text-sm text-ink-soft hover:text-ink flex items-center gap-2">
        <LeagueBadge league={fx.league} />
        <span className="truncate">{fx.home.name} v {fx.away.name}</span>
        <span className="ml-auto shrink-0">
          {dayLabel(fx.kickoff)}, {kickoffTime(fx.kickoff)}
        </span>
      </Link>
      <div className="px-4 pb-3 flex items-center gap-3">
        <div className="min-w-0">
          <p className="font-display text-2xl font-semibold leading-tight">{pickLabel(tip, fx)}</p>
          <p className="text-sm text-ink-soft">
            {tip.stake_units} unit{tip.stake_units === 1 ? '' : 's'}
            {tip.bookmaker ? ` at ${tip.bookmaker}` : ''}
          </p>
        </div>
        <div className="ml-auto">
          <Price value={tip.odds} />
        </div>
      </div>
      {tip.reasoning && <p className="px-4 pb-3 text-[15px] leading-relaxed text-ink/85">{tip.reasoning}</p>}
      <div className="mt-auto px-4 py-2 border-t border-dashed border-ink/15 flex items-center gap-2 text-sm">
        <span className="text-ink-soft">Confidence</span>
        <span className="flex gap-0.5" aria-label={`${tip.confidence} out of 5`}>
          {[1, 2, 3, 4, 5].map((n) => (
            <span key={n} className={`h-2 w-4 rounded-sm ${n <= tip.confidence ? 'bg-amber' : 'bg-ink/10'}`} />
          ))}
        </span>
        {tip.status !== 'pending' && (
          <span className={`ml-auto rounded px-2 py-0.5 font-semibold capitalize ${STATUS[tip.status]}`}>
            {tip.status} {tip.status !== 'void' && `${signed(tip.profit_units)}u`}
          </span>
        )}
        {fx.home_goals != null && tip.status !== 'pending' && (
          <span className="num text-base">
            {fx.home_goals}–{fx.away_goals}
          </span>
        )}
      </div>
    </article>
  )
}
