import { useState } from 'react'
import { MARKET_LABELS, odds, pct } from '../lib/format.js'

function selectionHeader(sel, fx) {
  if (sel === 'home') return fx.home.name
  if (sel === 'away') return fx.away.name
  return sel[0].toUpperCase() + sel.slice(1)
}

// One market as a bookmaker × selection grid. Best price per selection is
// highlighted; the footer shows the margin-free consensus ("fair") price and how
// far the best price sits above it. `onPick` makes prices clickable (admin).
function MarketTable({ market, fx, onPick }) {
  const books = [...new Set(market.selections.flatMap((s) => s.prices.map((p) => p.bookmaker)))].sort()
  const priceOf = (sel, book) => sel.prices.find((p) => p.bookmaker === book)?.price
  const title = market.market === 'OU' ? `${MARKET_LABELS.OU}, ${market.line} line` : MARKET_LABELS[market.market]

  const cell = (sel, book, price) => {
    const isBest = price === sel.best
    const pick = () => onPick({ market: market.market, selection: sel.selection, line: market.line, odds: price, bookmaker: book })
    const cls = `num text-base w-full rounded px-2 py-1 ${isBest ? 'bg-amber text-ink font-semibold' : ''} ${
      onPick ? 'hover:bg-ink hover:text-amber cursor-pointer' : ''
    }`
    return onPick ? (
      <button type="button" className={cls} onClick={pick} title={`Use ${odds(price)} at ${book}`}>
        {odds(price)}
      </button>
    ) : (
      <span className={`block ${cls}`}>{odds(price)}</span>
    )
  }

  return (
    <div className="panel overflow-hidden">
      <div className="px-4 py-2.5 border-b border-ink/10 flex flex-wrap items-baseline gap-x-3">
        <h3 className="text-lg">{title}</h3>
        {market.avg_margin != null && (
          <span className="ml-auto text-sm text-ink-soft">Average bookmaker margin {pct(market.avg_margin)}</span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-ink-soft">
              <th className="text-left font-medium px-4 py-2">Bookmaker</th>
              {market.selections.map((s) => (
                <th key={s.selection} className="font-medium px-2 py-2 text-center min-w-[5.5rem]">
                  {selectionHeader(s.selection, fx)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-ink/5">
            {books.map((b) => (
              <tr key={b}>
                <td className="px-4 py-1.5 whitespace-nowrap">{b}</td>
                {market.selections.map((s) => {
                  const p = priceOf(s, b)
                  return (
                    <td key={s.selection} className="px-2 py-1 text-center">
                      {p ? cell(s, b, p) : <span className="text-ink-faint">–</span>}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-ink/[0.03] border-t border-ink/10">
            <tr>
              <td className="px-4 py-2 font-semibold">Fair price</td>
              {market.selections.map((s) => (
                <td key={s.selection} className="px-2 py-2 text-center num text-base">
                  {odds(s.fair)}
                </td>
              ))}
            </tr>
            <tr>
              <td className="px-4 pb-2 text-ink-soft" title="Best price compared with the fair price">
                Best vs fair
              </td>
              {market.selections.map((s) => (
                <td
                  key={s.selection}
                  className={`px-2 pb-2 text-center num text-base ${s.edge > 0 ? 'text-pitch font-semibold' : 'text-ink-soft'}`}
                >
                  {s.edge == null ? '–' : `${s.edge > 0 ? '+' : ''}${pct(s.edge)}`}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}

export default function OddsBoard({ board, fx, onPick }) {
  const [allLines, setAllLines] = useState(false)
  const primary = board.markets.filter((m) => m.market !== 'OU' || m.line === board.main_ou_line)
  const extra = board.markets.filter((m) => !primary.includes(m))
  const shown = allLines ? board.markets : primary
  return (
    <div className="space-y-4">
      {shown.map((m) => (
        <MarketTable key={`${m.market}-${m.line}`} market={m} fx={fx} onPick={onPick} />
      ))}
      {extra.length > 0 && (
        <button type="button" className="btn-ghost" onClick={() => setAllLines((v) => !v)}>
          {allLines ? 'Show main goal line only' : `Show ${extra.length} more goal line${extra.length === 1 ? '' : 's'}`}
        </button>
      )}
    </div>
  )
}
