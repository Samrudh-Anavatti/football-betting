import { shortDate } from '../lib/format.js'

// Both XIs on one pitch: the away team in the top half attacking down, the home team in
// the bottom half attacking up. Before line-ups are out each side shows the XI it started
// its previous match with; anyone on this match's injury list gets a red marker.

const DEFAULT_KIT = {
  home: { primary: '0f1f36', number: 'ffffff', border: '0f1f36' },
  away: { primary: 'f2b705', number: '0f1f36', border: 'f2b705' },
}

const hex = (c) => `#${(c || '').replace('#', '')}`
function rgb(c) {
  const n = parseInt((c || '000000').replace('#', ''), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}
const clash = (a, b) => {
  const [x, y] = [rgb(a), rgb(b)]
  return Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]) < 110
}

// Rows from API-Football's grid ("row:col", row 1 the goalkeeper, col 1 the team's right),
// or from the formation string when a league doesn't send the grid.
function rows(team) {
  const xi = team.start_xi || []
  if (xi.length && xi.every((p) => p.grid)) {
    const byRow = {}
    for (const p of xi) {
      const [r, c] = p.grid.split(':').map(Number)
      ;(byRow[r] ||= []).push({ ...p, col: c })
    }
    return Object.keys(byRow)
      .map(Number)
      .sort((a, b) => a - b)
      .map((r) => byRow[r].sort((a, b) => a.col - b.col))
  }
  const shape = [1, ...(team.formation || '4-4-2').split('-').map(Number)]
  const out = []
  let i = 0
  for (const n of shape) {
    out.push(xi.slice(i, i + n))
    i += n
  }
  return out.filter((r) => r.length)
}

// Percent positions on the pitch. The bottom team's right is the screen's right; the top team's is the left.
function place(team, top) {
  const rs = rows(team)
  const out = []
  rs.forEach((row, ri) => {
    const depth = rs.length > 1 ? ri / (rs.length - 1) : 0 // 0 = goalkeeper, 1 = front line
    const y = 94 - depth * 37 // bottom half: 94% (keeper) up to 57%
    row.forEach((p, ci) => {
      const across = 9 + ((ci + 0.5) / row.length) * 82
      out.push({ ...p, x: top ? across : 100 - across, y: top ? 100 - y : y, keeper: ri === 0 })
    })
  })
  return out
}

// "D. Rice" -> "Rice", "Gabriel Magalhães" -> "Magalhães"; the full name is in the tooltip.
const surname = (name = '') => (name.includes('. ') ? name.split('. ').slice(1).join('. ') : name.split(' ').slice(-1)[0])

function Player({ p, kit, out }) {
  const k = p.keeper ? kit.goalkeeper || kit.player : kit.player
  return (
    <div
      className="absolute flex w-[18%] max-w-[4.75rem] -translate-x-1/2 -translate-y-1/2 flex-col items-center"
      style={{ left: `${p.x}%`, top: `${p.y}%` }}
      title={`${p.name}${p.number != null ? `, ${p.number}` : ''}${out ? `. Out for this match: ${out}` : ''}`}
    >
      <span
        className={`relative grid h-7 w-7 place-items-center rounded-full border-2 font-display text-[13px] font-bold tabular-nums shadow-[0_2px_4px_rgba(0,0,0,0.35)] ${out ? 'opacity-60' : ''}`}
        style={{ background: hex(k.primary), color: hex(k.number), borderColor: hex(k.border) }}
      >
        {p.number ?? ''}
        {out && (
          <span aria-hidden className="absolute -right-2.5 -top-1.5 h-3 w-2.5 rotate-12 rounded-[2px] bg-red ring-1 ring-white" />
        )}
      </span>
      <span
        className={`mt-0.5 max-w-full truncate rounded-[3px] px-1 text-[11px] font-semibold leading-4 text-white ${out ? 'bg-red/90' : 'bg-ink/45'}`}
      >
        {surname(p.name)}
      </span>
    </div>
  )
}

function PitchLines() {
  // FIFA proportions on a 68 x 105 pitch.
  return (
    <svg aria-hidden viewBox="0 0 68 105" className="absolute inset-0 h-full w-full">
      <g fill="none" stroke="white" strokeOpacity="0.5" strokeWidth="0.35">
        <rect x="1.5" y="1.5" width="65" height="102" />
        <line x1="1.5" y1="52.5" x2="66.5" y2="52.5" />
        <circle cx="34" cy="52.5" r="9.15" />
        <rect x="13.84" y="1.5" width="40.32" height="16.5" />
        <rect x="24.84" y="1.5" width="18.32" height="5.5" />
        <rect x="13.84" y="87" width="40.32" height="16.5" />
        <rect x="24.84" y="98" width="18.32" height="5.5" />
        <path d="M26.7 18 a9.15 9.15 0 0 0 14.6 0" />
        <path d="M26.7 87 a9.15 9.15 0 0 1 14.6 0" />
      </g>
      <g fill="white" fillOpacity="0.6">
        <circle cx="34" cy="52.5" r="0.5" />
        <circle cx="34" cy="12.5" r="0.4" />
        <circle cx="34" cy="92.5" r="0.4" />
      </g>
    </svg>
  )
}

function TeamLine({ team, side, fx }) {
  const t = fx[side]
  const m = team.previous_match
  return (
    <div className="flex items-start gap-3">
      {t.logo ? <img src={t.logo} alt="" className="mt-0.5 h-6 w-6 shrink-0 object-contain" /> : null}
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-display font-bold">{t.name}</span>
          {team.formation && <span className="num text-sm font-semibold text-ink-soft">{team.formation}</span>}
        </p>
        <p className="text-sm text-ink-soft">
          {team.source === 'confirmed'
            ? 'Confirmed line-up'
            : m
              ? `Last match: ${m.result} ${m.gf}–${m.ga} ${m.venue === 'H' ? 'v' : 'at'} ${m.opponent}, ${shortDate(m.date)}`
              : 'No line-up yet'}
        </p>
      </div>
      <a
        href={team.transfermarkt}
        target="_blank"
        rel="noopener noreferrer"
        className="link shrink-0 inline-flex items-center gap-1 text-sm"
        title={`${t.name} squad and market values on Transfermarkt`}
      >
        Transfermarkt
        <svg aria-hidden viewBox="0 0 12 12" className="h-3 w-3">
          <path d="M4 2h6v6M10 2 3 9" fill="none" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      </a>
    </div>
  )
}

export default function PitchCard({ pitch, fx, injuries }) {
  if (!pitch) return null
  const { home, away } = pitch
  const hasHome = home.start_xi?.length > 0
  const hasAway = away.start_xi?.length > 0
  const out = Object.fromEntries((injuries || []).filter((i) => i.player_id).map((i) => [i.player_id, i.reason || i.type || 'injured']))
  const homeKit = home.colors || { player: DEFAULT_KIT.home }
  let awayKit = away.colors || { player: DEFAULT_KIT.away }
  if (clash(homeKit.player?.primary, awayKit.player?.primary)) {
    // Two similar kits: draw the away side in white with its colour as the outline.
    awayKit = { ...awayKit, player: { primary: 'fbfcfa', number: awayKit.player?.primary || '0f1f36', border: awayKit.player?.primary || '0f1f36' } }
  }
  const players = [
    ...(hasAway ? place(away, true).map((p) => ({ p, kit: awayKit })) : []),
    ...(hasHome ? place(home, false).map((p) => ({ p, kit: homeKit })) : []),
  ]
  const confirmed = home.source === 'confirmed' && away.source === 'confirmed'
  const anyOut = players.some(({ p }) => out[p.id])

  return (
    <div className="panel p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="text-lg">Line-ups</h3>
        <span
          className={`rounded-[4px] px-1.5 py-0.5 text-xs font-bold ${confirmed ? 'bg-pitch text-white' : 'bg-ink/[0.07] text-ink-soft'}`}
        >
          {confirmed ? 'Confirmed' : 'Last starting XI'}
        </span>
      </div>
      <TeamLine team={away} side="away" fx={fx} />
      <div
        className="relative mx-auto aspect-[68/105] w-full max-w-[26rem] overflow-hidden rounded-lg shadow-[inset_0_0_0_1px_rgba(0,0,0,0.15)]"
        style={{
          background:
            'repeating-linear-gradient(to bottom, #2c7a4b 0 7.14%, #286f45 7.14% 14.28%)',
        }}
        role="img"
        aria-label={`${fx.away.name} ${away.formation || ''} at the top, ${fx.home.name} ${home.formation || ''} at the bottom`}
      >
        <PitchLines />
        {players.map(({ p, kit }, i) => (
          <Player key={`${p.id ?? p.name}-${i}`} p={p} kit={kit} out={out[p.id]} />
        ))}
        {(!hasHome || !hasAway) && (
          <p className={`absolute inset-x-0 ${!hasAway ? 'top-[22%]' : 'bottom-[22%]'} text-center text-sm font-medium text-white/80`}>
            {fx[!hasAway ? 'away' : 'home'].name}'s line-up isn't in yet
          </p>
        )}
      </div>
      <TeamLine team={home} side="home" fx={fx} />
      {!confirmed && (
        <p className="text-xs text-ink-soft">
          Each side as it started its last match, so rotation can change it.{' '}
          {anyOut && 'A red marker means the player is on this match’s injury or suspension list. '}
          Confirmed line-ups replace these about an hour before kick-off.
        </p>
      )}
    </div>
  )
}
