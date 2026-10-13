import { ago, ageHours, odds } from '../lib/format.js'

// A price cell. `board` is the shop-board look (amber on ink) for a price that's been taken;
// `best` marks the best on offer; clickable cells flip to the board look on hover.
export function Price({ value, label, best, board, onClick, title }) {
  const Tag = onClick ? 'button' : 'span'
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      title={title}
      className={`price group/price ${board ? 'price-board' : best ? 'price-best' : ''} ${onClick ? 'price-hit' : ''}`}
    >
      {label && (
        <span className={`text-[10px] font-sans font-medium mb-0.5 ${board ? 'text-white/60' : 'text-ink-soft group-hover/price:text-white/60'}`}>
          {label}
        </span>
      )}
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
          className={`h-6 w-6 rounded-[4px] grid place-items-center font-display font-bold text-sm ${FORM_STYLE[m.result]}`}
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
    <div className="rounded-xl border border-dashed border-ink/20 px-5 py-8 text-center">
      <p className="font-display text-lg font-bold">{title}</p>
      {children && <div className="mt-1 text-ink-soft max-w-prose mx-auto">{children}</div>}
    </div>
  )
}

export function ErrorNote({ error, children }) {
  if (!error && !children) return null
  return (
    <div role="alert" className="rounded-md border-l-4 border-red bg-red-light px-3 py-2 text-sm text-red">
      {children || error.message}
    </div>
  )
}

// Skeleton rows in the shape of the list that's loading.
export function Loading({ label = 'Loading', rows = 3 }) {
  return (
    <div className="space-y-2 py-2" aria-busy="true">
      <span className="sr-only">{label}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-12 rounded-lg bg-ink/[0.06] animate-pulse" style={{ opacity: 1 - i * 0.25 }} />
      ))}
    </div>
  )
}

// Section heading ruled across the page like a form guide, with an optional count at the end of the rule.
export function SectionHead({ title, count, children }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-4">
      <h2 className="text-2xl sm:text-[1.7rem] leading-none">{title}</h2>
      {count != null && <span className="num text-lg font-bold text-ink-faint">{count}</span>}
      <span aria-hidden className="hidden sm:block flex-1 self-center border-t-2 border-ink/80" />
      {children && <div className="ml-auto sm:ml-0 flex items-center gap-3 text-sm">{children}</div>}
    </div>
  )
}
