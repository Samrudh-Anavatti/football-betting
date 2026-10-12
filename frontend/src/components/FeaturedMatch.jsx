import { Link } from 'react-router-dom'
import { dayLabel, kickoffTime } from '../lib/format.js'
import ProbabilityStrip from './ProbabilityStrip.jsx'
import { LeagueBadge, Price, TeamName } from './ui.jsx'

// The home banner's preview of what a match page holds: a real upcoming match
// with its best prices and the AI's read. The whole card opens the match.
export default function FeaturedMatch({ data }) {
  if (!data?.ai) return null
  const { fixture: fx, ai } = data
  const a = ai.analysis
  const best = fx.best_1x2
  return (
    <Link
      to={`/match/${fx.id}`}
      className="group block min-w-0 rounded-md bg-chalk text-ink border-t-[6px] border-amber px-4 pt-3 pb-4 space-y-3 shadow-[0_12px_32px_-12px_rgba(0,0,0,0.5)] lg:rotate-[1.5deg] transition-transform hover:rotate-0 focus-visible:rotate-0 focus-visible:ring-offset-ink"
    >
      <p className="flex items-center gap-1.5 text-sm text-ink-soft">
        <LeagueBadge league={fx.league} />
        <span className="truncate">{fx.league.name}</span>
        <span className="ml-auto whitespace-nowrap">
          {dayLabel(fx.kickoff)}, {kickoffTime(fx.kickoff)}
        </span>
      </p>
      <div className="font-display text-2xl font-semibold leading-tight space-y-0.5">
        <div><TeamName team={fx.home} className="max-w-full" /></div>
        <div><TeamName team={fx.away} className="max-w-full" /></div>
      </div>
      <ProbabilityStrip ai={a.probabilities} market={ai.market_probs?.result} fx={fx} />
      {best && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-ink-soft mr-auto">Best prices</span>
          <Price value={best.home} label="Home" />
          <Price value={best.draw} label="Draw" />
          <Price value={best.away} label="Away" />
        </div>
      )}
      <p className="text-sm leading-snug line-clamp-3">
        <span className="font-semibold">The AI's read: </span>
        {a.summary}
      </p>
      <p className="text-sm font-semibold underline decoration-amber decoration-2 underline-offset-4 group-hover:decoration-ink">
        Open any match for odds, stats and AI analysis
      </p>
    </Link>
  )
}
