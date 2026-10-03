import { LeagueBadge } from './ui.jsx'

// Country / league chips. `value` is a league id or null for "All".
export default function LeagueFilter({ leagues, value, onChange }) {
  const chip = (active) =>
    `shrink-0 rounded-full px-3 py-1 text-sm font-semibold border transition ${
      active ? 'bg-ink text-white border-ink' : 'bg-white border-ink/15 text-ink hover:border-ink/40'
    }`
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 -mx-4 px-4 sm:mx-0 sm:px-0 sm:flex-wrap">
      <button type="button" className={chip(value == null)} onClick={() => onChange(null)}>
        All leagues
      </button>
      {leagues.map((lg) => (
        <button key={lg.id} type="button" className={chip(value === lg.id)} onClick={() => onChange(lg.id)} title={lg.country}>
          <span className="inline-flex items-center gap-1.5">
            <LeagueBadge league={lg} />
            {lg.name}
          </span>
        </button>
      ))}
    </div>
  )
}
