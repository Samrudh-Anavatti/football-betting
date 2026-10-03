import { ago, ageHours, odds } from '../lib/format.js'

export function Price({ value, label, best, onClick, title }) {
  const Tag = onClick ? 'button' : 'span'
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      title={title}
      className={`price ${best ? 'ring-2 ring-amber' : ''} ${onClick ? 'hover:bg-ink/85 cursor-pointer' : ''}`}
    >
      {label && <span className="text-[10px] font-sans font-medium text-white/60 mb-0.5">{label}</span>}
      <span className="text-lg">{odds(value)}</span>
    </Tag>
  )
}

const FORM_STYLE = {
  W: 'bg-pitch text-white',
  D: 'bg-ink/15 text-ink',
  L: 'bg-red text-white',
}

export function FormStrip({ form }) {
  if (!form?.length) return <span className="text-sm text-ink-faint">No recent results</span>
  return (
    <span className="inline-flex gap-1">
      {form.map((m, i) => (
        <span
          key={i}
          title={`${m.home} ${m.hg}–${m.ag} ${m.away}`}
          className={`h-6 w-6 rounded-sm grid place-items-center font-display font-bold text-sm ${FORM_STYLE[m.result]}`}
        >
          {m.result}
        </span>
      ))}
    </span>
  )
}

// "Updated 3 h ago", turning amber then red as data ages past the thresholds (hours).
export function Freshness({ at, warnAfter = 24, staleAfter = 24 * 7, prefix = 'Updated' }) {
  const h = ageHours(at)
  const tone = !at ? 'text-ink-faint' : h > staleAfter ? 'text-red' : h > warnAfter ? 'text-amber-dark' : 'text-pitch'
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm ${tone}`}>
      <span className="h-2 w-2 rounded-full bg-current" aria-hidden />
      {at ? `${prefix} ${ago(at)}` : 'Not fetched yet'}
    </span>
  )
}

// League logo from the API when we have it; Windows can't render flag emoji.
export function LeagueBadge({ league, className = 'h-4 w-4' }) {
  return league.logo ? (
    <img src={league.logo} alt="" className={`${className} object-contain shrink-0`} loading="lazy" />
  ) : (
    <span aria-hidden className="shrink-0">{league.flag}</span>
  )
}

export function TeamName({ team, align = 'left', className = '' }) {
  return (
    <span className={`inline-flex items-center gap-2 min-w-0 ${align === 'right' ? 'flex-row-reverse text-right' : ''} ${className}`}>
      {team.logo ? (
        <img src={team.logo} alt="" className="h-5 w-5 object-contain shrink-0" loading="lazy" />
      ) : (
        <span className="h-5 w-5 rounded-full bg-ink/10 shrink-0" aria-hidden />
      )}
      <span className="truncate">{team.name}</span>
    </span>
  )
}

export function Empty({ title, children }) {
  return (
    <div className="panel px-5 py-8 text-center">
      <p className="font-display text-xl font-semibold">{title}</p>
      {children && <div className="mt-1 text-ink-soft">{children}</div>}
    </div>
  )
}

export function ErrorNote({ error, children }) {
  if (!error && !children) return null
  return (
    <div className="rounded-md border border-red/30 bg-red-light px-3 py-2 text-sm text-red">
      {children || error.message}
    </div>
  )
}

export function Loading({ label = 'Loading' }) {
  return <p className="text-ink-soft py-6">{label}…</p>
}

export function SectionHead({ title, children }) {
  return (
    <div className="flex flex-wrap items-end gap-x-4 gap-y-1 mb-3">
      <h2 className="text-2xl">{title}</h2>
      <div className="ml-auto flex items-center gap-3">{children}</div>
    </div>
  )
}
