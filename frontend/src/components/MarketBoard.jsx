import { useMemo, useState } from 'react'
import { odds, pct, teamify } from '../lib/format.js'

// The full market board: every market our bookmakers price for this match,
// grouped into categories. Each selection shows the best price (click it to
// make a pick), the margin-free fair price and how far the best sits above it.

const LIST_PREVIEW = 12

// API-Football's names, where they don't read well with team names swapped in.
const MARKET_NAMES = { 'Home/Away': 'Draw no bet' }
const marketName = (m, fx) => MARKET_NAMES[m.name] || teamify(m.name, fx)
const LINES_AROUND_MAIN = 2

function Edge({ edge }) {
  if (edge == null) return null
  return (
    <span className={`num text-sm ${edge > 0 ? 'text-pitch font-semibold' : 'text-ink-faint'}`}>
      {edge > 0 ? '+' : ''}
      {pct(edge)}
    </span>
  )
}

function PriceButton({ sel, market, onPick, size = 'md' }) {
  const pick = onPick
    ? () =>
        onPick({
          market_id: market.id,
          market: market.name,
          selection: sel.value,
          line: sel.line,
          odds: sel.best,
          bookmaker: sel.best_bookmaker,
        })
    : undefined
  const Tag = pick ? 'button' : 'span'
  return (
    <Tag
      type={pick ? 'button' : undefined}
      onClick={pick}
      title={`Best price ${odds(sel.best)} at ${sel.best_bookmaker}${pick ? ', click to use it' : ''}`}
      className={`price ${size === 'sm' ? 'min-w-[3rem] py-1' : ''} ${sel.edge > 0 ? 'ring-2 ring-pitch' : ''} ${
        pick ? 'hover:bg-ink/85 cursor-pointer' : ''
      }`}
    >
      <span className={size === 'sm' ? 'text-base' : 'text-lg'}>{odds(sel.best)}</span>
    </Tag>
  )
}

// One selection: label, best price, and fair/edge underneath.
function SelTile({ sel, market, fx, onPick, label }) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-ink/10 px-3 py-2 min-w-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium leading-tight truncate" title={teamify(sel.value, fx)}>
          {label ?? teamify(sel.value, fx)}
        </p>
        <p className="text-xs text-ink-soft truncate">
          {sel.best_bookmaker}
          {sel.fair != null && (
            <>
              {' · fair '}
              <span className="num text-sm">{odds(sel.fair)}</span>{' '}
              <Edge edge={sel.edge} />
            </>
          )}
        </p>
      </div>
      <PriceButton sel={sel} market={market} onPick={onPick} />
    </div>
  )
}

function sideLabel(side, fx) {
  if (side === 'Home') return fx.home.name
  if (side === 'Away') return fx.away.name
  return side
}

// Over/under and handicap markets: one row per line, sides as columns.
function LinesTable({ market, fx, onPick }) {
  const [all, setAll] = useState(false)
  const idx = Math.max(0, market.groups.findIndex((g) => g.line === market.main_line))
  const shown = all ? market.groups : market.groups.slice(Math.max(0, idx - LINES_AROUND_MAIN), idx + LINES_AROUND_MAIN + 1)
  const sides = [...new Set(market.groups.flatMap((g) => g.selections.map((s) => s.side)))]
  const isHandicap = /handicap/i.test(market.name)
  return (
    <div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-ink-soft">
            <th className="text-left font-medium py-1 pr-2">{isHandicap ? `${fx.home.name} line` : 'Line'}</th>
            {sides.map((s) => (
              <th key={s} className="font-medium py-1 px-1 text-center truncate max-w-[8rem]">
                {sideLabel(s, fx)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink/5">
          {shown.map((g) => (
            <tr key={g.line} className={g.line === market.main_line ? 'bg-amber-light/50' : ''}>
              <td className="py-1.5 pr-2 num text-base font-semibold whitespace-nowrap">
                {g.line > 0 && isHandicap ? '+' : ''}
                {g.line}
              </td>
              {sides.map((side) => {
                const sel = g.selections.find((s) => s.side === side)
                return (
                  <td key={side} className="py-1 px-1 text-center">
                    {sel ? (
                      <div className="inline-flex flex-col items-center gap-0.5">
                        <PriceButton sel={sel} market={market} onPick={onPick} size="sm" />
                        <Edge edge={sel.edge} />
                      </div>
                    ) : (
                      <span className="text-ink-faint">–</span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {market.groups.length > shown.length || all ? (
        <button type="button" className="mt-2 text-sm font-semibold underline underline-offset-4" onClick={() => setAll((v) => !v)}>
          {all ? 'Show lines near the main one' : `Show all ${market.groups.length} lines`}
        </button>
      ) : null}
    </div>
  )
}

// Every bookmaker's price for a set of selections.
function BookTable({ selections, bookmakers, fx }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-ink-soft">
            <th className="text-left font-medium py-1 pr-3">Bookmaker</th>
            {selections.map((s) => (
              <th key={s.value} className="font-medium px-2 py-1 text-center min-w-[4.5rem]">
                {teamify(s.value, fx)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink/5">
          {bookmakers.map((b, i) => (
            <tr key={b}>
              <td className="py-1 pr-3 whitespace-nowrap">{b}</td>
              {selections.map((s) => {
                const p = s.prices[i]
                return (
                  <td key={s.value} className={`px-2 py-1 text-center num text-base ${p && p === s.best ? 'font-bold' : ''}`}>
                    {p ? odds(p) : <span className="text-ink-faint">–</span>}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
        <tfoot className="border-t border-ink/10">
          <tr>
            <td className="py-1 pr-3 font-semibold">Fair price</td>
            {selections.map((s) => (
              <td key={s.value} className="px-2 py-1 text-center num text-base">
                {odds(s.fair)}
              </td>
            ))}
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function bestEdge(market) {
  let best = null
  for (const g of market.groups) for (const s of g.selections) if (s.edge != null && (best == null || s.edge > best)) best = s.edge
  return best
}

function MarketCard({ market, fx, onPick, bookmakers, defaultOpen, filter }) {
  const [open, setOpen] = useState(defaultOpen)
  const [compare, setCompare] = useState(false)
  const [all, setAll] = useState(false)
  const edge = bestEdge(market)
  const margin = market.groups.find((g) => g.line === market.main_line)?.margin ?? market.groups[0]?.margin

  const selections = market.groups[0].selections.filter(
    (s) => !filter || teamify(s.value, fx).toLowerCase().includes(filter) || market.name.toLowerCase().includes(filter),
  )
  const compareSels =
    market.layout === 'lines'
      ? (market.groups.find((g) => g.line === market.main_line) || market.groups[0]).selections
      : selections.slice(0, market.layout === 'list' ? 8 : selections.length)

  return (
    <section className="panel overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full px-4 py-2.5 flex items-center gap-3 text-left hover:bg-chalk/60"
      >
        <h3 className="text-lg leading-tight min-w-0 truncate">{marketName(market, fx)}</h3>
        {edge > 0 && (
          <span className="shrink-0 rounded bg-pitch-light text-pitch text-xs font-semibold px-1.5 py-0.5">
            best +{pct(edge)}
          </span>
        )}
        <span className="ml-auto shrink-0 text-xs text-ink-soft">
          {market.layout === 'lines' ? `${market.groups.length} line${market.groups.length === 1 ? '' : 's'} · ` : market.layout === 'list' ? `${market.groups[0].selections.length} options · ` : ''}
          {market.bookmakers} book{market.bookmakers === 1 ? '' : 's'}
          {margin != null && ` · margin ${pct(margin)}`}
        </span>
        <span aria-hidden className={`shrink-0 text-ink-soft transition-transform ${open ? 'rotate-90' : ''}`}>
          ›
        </span>
      </button>
      {open && (
        <div className="px-4 pb-3 pt-1 space-y-3 border-t border-ink/5">
          {market.layout === 'lines' ? (
            <LinesTable market={market} fx={fx} onPick={onPick} />
          ) : (
            <>
              <div className={`grid gap-2 ${market.layout === 'list' ? 'sm:grid-cols-2' : selections.length >= 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2'}`}>
                {(market.layout === 'list' && !all && !filter ? selections.slice(0, LIST_PREVIEW) : selections).map((s) => (
                  <SelTile key={s.value} sel={s} market={market} fx={fx} onPick={onPick} />
                ))}
              </div>
              {market.layout === 'list' && !filter && selections.length > LIST_PREVIEW && (
                <button type="button" className="text-sm font-semibold underline underline-offset-4" onClick={() => setAll((v) => !v)}>
                  {all ? 'Show the shortest prices only' : `Show all ${selections.length}`}
                </button>
              )}
            </>
          )}
          {market.bookmakers > 1 && (
            <div>
              <button type="button" className="text-sm text-ink-soft font-semibold hover:text-ink" onClick={() => setCompare((v) => !v)}>
                {compare ? 'Hide bookmakers' : 'Compare bookmakers'}
              </button>
              {compare && (
                <div className="mt-2">
                  <BookTable selections={compareSels} bookmakers={bookmakers} fx={fx} />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

export default function MarketBoard({ board, fx, onPick }) {
  const [cat, setCat] = useState(board.categories[0]?.key || 'main')
  const [query, setQuery] = useState('')
  const q = query.trim().toLowerCase()

  const shown = useMemo(() => {
    if (!q) return board.markets.filter((m) => m.category === cat)
    return board.markets.filter(
      (m) =>
        marketName(m, fx).toLowerCase().includes(q) ||
        m.groups.some((g) => g.selections.some((s) => teamify(s.value, fx).toLowerCase().includes(q))),
    )
  }, [board.markets, cat, q, fx])

  return (
    <div className="space-y-3 min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1 overflow-x-auto -mx-1 px-1 pb-1 min-w-0 w-full sm:w-auto sm:flex-1" role="tablist" aria-label="Market categories">
          {board.categories.map((c) => {
            const on = !q && c.key === cat
            return (
              <button
                key={c.key}
                type="button"
                role="tab"
                aria-selected={on}
                onClick={() => {
                  setCat(c.key)
                  setQuery('')
                }}
                className={`shrink-0 rounded-md px-3 py-1.5 text-sm font-semibold border ${
                  on ? 'bg-ink text-white border-ink' : 'border-ink/15 hover:border-ink/40'
                }`}
              >
                {c.label} <span className={on ? 'text-white/60' : 'text-ink-faint'}>{c.count}</span>
              </button>
            )
          })}
        </div>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Find a market or player"
          aria-label="Find a market or player"
          className="input py-1.5 sm:max-w-[14rem] sm:ml-auto"
        />
      </div>
      <p className="text-xs text-ink-soft">
        Best price from {board.bookmakers.join(', ')}. Fair is the price with the bookmakers' margin removed; green means
        the best price is above it.
      </p>
      {shown.length === 0 ? (
        <p className="text-sm text-ink-faint py-4">No markets match “{query}”.</p>
      ) : (
        shown.map((m, i) => (
          <MarketCard
            key={`${m.id}-${q}`}
            market={m}
            fx={fx}
            onPick={onPick}
            bookmakers={board.bookmakers}
            filter={q && !marketName(m, fx).toLowerCase().includes(q) ? q : ''}
            defaultOpen={cat === 'main' || i < 4 || !!q}
          />
        ))
      )}
    </div>
  )
}
