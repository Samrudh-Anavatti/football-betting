import { Link } from 'react-router-dom'
import { dayLabel, kickoffTime } from '../lib/format.js'
import ProbabilityStrip from './ProbabilityStrip.jsx'
import { LeagueBadge, Price, TeamName } from './ui.jsx'

// The home banner's preview of what a match page holds: a real upcoming match
// with its best prices and the AI's read, printed as a betting slip. The whole slip opens the match.
export default function FeaturedMatch({ data }) {
  if (!data?.ai) return null
  const { fixture: fx, ai } = data
  const a = ai.analysis
  const best = fx.best_1x2
  return (
    <Link
      to={`/match/${fx.id}`}
      className="group block min-w-0 rounded-lg lg:rotate-[2deg] transition-transform duration-300 ease-out hover:rotate-0 hover:-translate-y-1 focus-visible:rotate-0 focus-visible:ring-offset-ink [filter:drop-shadow(0_18px_28px_rgba(2,8,20,0.55))]"
    >
      <div className="perforated rounded-t-lg bg-paper text-ink">
        <div className="h-1.5 rounded-t-lg bg-amber" />
        <div className="px-5 pt-3.5 pb-6 space-y-4">
          <p className="flex items-center gap-1.5 text-sm text-ink-soft">
            <LeagueBadge league={fx.league} />
            <span className="truncate">{fx.league.name}</span>
            <span className="ml-auto whitespace-nowrap num font-semibold text-ink">
              {dayLabel(fx.kickoff)}, {kickoffTime(fx.kickoff)}
            </span>
          </p>
          <div className="font-display text-[1.6rem] font-extrabold leading-[1.1] tracking-tight space-y-0.5 [font-stretch:108%]">
            <div><TeamName team={fx.home} className="max-w-full" /></div>
            <div><TeamName team={fx.away} className="max-w-full" /></div>
          </div>
          <ProbabilityStrip ai={a.probabilities} market={ai.market_probs?.result} fx={fx} />
          {best && (
            <div className="flex items-center gap-1.5 border-y border-dashed border-ink/20 py-3">
              <span className="text-sm text-ink-soft mr-auto">Best prices</span>
              <Price value={best.home} label="Home" board />
              <Price value={best.draw} label="Draw" board />
              <Price value={best.away} label="Away" board />
            </div>
          )}
          <p className="text-sm leading-snug line-clamp-3 text-ink/85">
            <span className="font-semibold text-ink">The AI's read: </span>
            {a.summary}
          </p>
          <p className="text-sm font-semibold underline decoration-amber decoration-2 underline-offset-4 transition-colors group-hover:decoration-ink">
            Open any match for odds, stats and AI analysis
          </p>
        </div>
      </div>
    </Link>
  )
}
