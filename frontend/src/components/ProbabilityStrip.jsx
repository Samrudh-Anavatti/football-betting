import { useEffect, useState } from 'react'

// Home / draw / away as one segmented bar: the AI's split on top, the bookmakers'
// margin-free split as a thin bar underneath, so disagreement shows at a glance.
// The AI bar fills once on mount (the global reduced-motion rule turns that off).

const SEGMENTS = [
  ['home', 'bg-ink'],
  ['draw', 'bg-ink/20'],
  ['away', 'bg-amber'],
]

function Bar({ split, height, grow }) {
  const total = SEGMENTS.reduce((s, [k]) => s + (split[k] || 0), 0) || 1
  return (
    <div className={`flex ${height} w-full gap-0.5 overflow-hidden rounded-sm`}>
      {SEGMENTS.map(([k, tone]) => (
        <div
          key={k}
          className={`${tone} transition-[width] duration-700 ease-out`}
          style={{ width: grow ? `${((split[k] || 0) / total) * 100}%` : '0%' }}
        />
      ))}
    </div>
  )
}

const whole = (p) => (p == null ? '–' : `${Math.round(p * 100)}%`)

export default function ProbabilityStrip({ ai, market, fx }) {
  const [grow, setGrow] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrow(true))
    return () => cancelAnimationFrame(id)
  }, [])
  const split = { home: ai.home_win, draw: ai.draw, away: ai.away_win }
  const names = { home: fx.home.name, draw: 'Draw', away: fx.away.name }
  return (
    <figure className="space-y-1.5">
      <figcaption className="sr-only">
        The AI gives {fx.home.name} {whole(split.home)}, the draw {whole(split.draw)} and {fx.away.name} {whole(split.away)}
        {market ? `; the bookmakers say ${whole(market.home)}, ${whole(market.draw)} and ${whole(market.away)}` : ''}.
      </figcaption>
      <div aria-hidden className="grid grid-cols-[3.75rem_1fr] items-center gap-x-2 gap-y-1">
        <span className="text-sm font-semibold">AI</span>
        <Bar split={split} height="h-3" grow={grow} />
        {market && (
          <>
            <span className="text-sm text-ink-soft">Market</span>
            <Bar split={market} height="h-1.5" grow />
          </>
        )}
      </div>
      <div aria-hidden className="ml-[4.25rem] grid grid-cols-3 text-sm">
        {SEGMENTS.map(([k], i) => (
          <span key={k} className={`min-w-0 leading-tight ${i === 1 ? 'text-center' : i === 2 ? 'text-right' : ''}`}>
            <span className="block num text-xl font-semibold">{whole(split[k])}</span>
            <span className="block truncate text-ink-soft">{names[k]}</span>
          </span>
        ))}
      </div>
    </figure>
  )
}
