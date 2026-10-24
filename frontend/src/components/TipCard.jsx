import { Link } from 'react-router-dom'
import { dayLabel, kickoffTime, pickLabel, signed } from '../lib/format.js'
import { LeagueBadge, Price } from './ui.jsx'

// Settled tips get a rubber stamp, slightly askew.
const STAMP = {
  won: 'border-pitch text-pitch',
  lost: 'border-red text-red',
  void: 'border-ink/40 text-ink-soft',
}

// A tip printed as a betting slip: the pick, the price taken, the stake, Ivo's reasoning.
export default function TipCard({ tip }) {
  const fx = tip.fixture
  const settled = tip.status !== 'pending'
  return (
    <div className="slip-shadow h-full transition-transform duration-200 hover:-translate-y-0.5">
      <article className="perforated h-full rounded-t-xl bg-paper flex flex-col">
        <Link
          to={`/match/${fx.id}`}
          className="px-4 pt-3.5 pb-2 text-sm text-ink-soft hover:text-ink flex items-center gap-2 transition-colors"
        >
          <LeagueBadge league={fx.league} />
          <span className="truncate font-medium">{fx.home.name} v {fx.away.name}</span>
          <span className="ml-auto shrink-0 num">
            {dayLabel(fx.kickoff)}, {kickoffTime(fx.kickoff)}
          </span>
        </Link>
        <div className="px-4 pb-3 flex items-start gap-3">
          <div className="min-w-0">
            <p className="font-display text-[1.35rem] font-extrabold leading-tight tracking-tight [font-stretch:108%]">
              {pickLabel(tip, fx)}
            </p>
            <p className="mt-0.5 text-sm text-ink-soft">
              {tip.stake_units} unit{tip.stake_units === 1 ? '' : 's'}
              {tip.bookmaker ? ` at ${tip.bookmaker}` : ''}
            </p>
          </div>
          <div className="ml-auto shrink-0">
            <Price value={tip.odds} board />
          </div>
        </div>
        {tip.reasoning && <p className="px-4 pb-3 text-[15px] leading-relaxed text-ink/80 max-w-prose">{tip.reasoning}</p>}
        <div className="mt-auto mx-4 pt-2.5 pb-5 border-t border-dashed border-ink/20 flex items-center gap-2 text-sm">
          <span className="text-ink-soft">Confidence</span>
          <span className="num font-semibold">{tip.confidence}/10</span>
          {settled && fx.home_goals != null && (
            <span className="ml-auto num font-bold text-base">
              {fx.home_goals}–{fx.away_goals}
            </span>
          )}
          {settled && (
            <span
              className={`${fx.home_goals == null ? 'ml-auto' : ''} -my-1 -rotate-[5deg] rounded-[4px] border-2 px-1.5 py-0.5 font-display font-extrabold leading-none tracking-tight capitalize ${STAMP[tip.status]}`}
            >
              {tip.status}
              {tip.status !== 'void' && <span className="num ml-1">{signed(tip.profit_units)}u</span>}
            </span>
          )}
        </div>
      </article>
    </div>
  )
}
