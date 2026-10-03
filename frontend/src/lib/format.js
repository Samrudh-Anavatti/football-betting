// Display helpers. API datetimes are ISO UTC; everything shows in the viewer's local time.

export const SELECTION_LABELS = {
  home: 'Home', draw: 'Draw', away: 'Away', over: 'Over', under: 'Under', yes: 'Yes', no: 'No',
}
export const MARKET_LABELS = { '1X2': 'Match result', OU: 'Total goals', BTTS: 'Both teams to score' }

export function pickLabel({ market, selection, line }, fixture) {
  if (market === '1X2') {
    if (selection === 'draw') return 'Draw'
    const team = fixture ? fixture[selection]?.name : SELECTION_LABELS[selection]
    return `${team} to win`
  }
  if (market === 'OU') return `${SELECTION_LABELS[selection]} ${line} goals`
  if (market === 'BTTS') return `Both teams to score: ${SELECTION_LABELS[selection]}`
  return `${market} ${selection}`
}

export const odds = (p) => (p == null ? '–' : Number(p).toFixed(2))
export const pct = (x, digits = 1) => (x == null ? '–' : `${(x * 100).toFixed(digits)}%`)
export const signed = (x, digits = 2) => (x == null ? '–' : `${x > 0 ? '+' : ''}${Number(x).toFixed(digits)}`)
export const money = (x) =>
  x == null ? '–' : `£${Number(x).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export function kickoffTime(iso) {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

export function dayLabel(iso) {
  const d = new Date(iso)
  const today = new Date()
  const diff = Math.round((new Date(d.toDateString()) - new Date(today.toDateString())) / 86400000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Tomorrow'
  if (diff === -1) return 'Yesterday'
  return d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
}

export function shortDate(iso) {
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' })
}

export function ago(iso) {
  if (!iso) return 'never'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  const d = Math.floor(s / 86400)
  return `${d} day${d === 1 ? '' : 's'} ago`
}

export function ageHours(iso) {
  return iso ? (Date.now() - new Date(iso).getTime()) / 3600000 : Infinity
}

export function groupBy(items, keyFn) {
  const out = []
  const idx = new Map()
  for (const it of items) {
    const k = keyFn(it)
    if (!idx.has(k)) {
      idx.set(k, out.length)
      out.push({ key: k, items: [] })
    }
    out[idx.get(k)].items.push(it)
  }
  return out
}
