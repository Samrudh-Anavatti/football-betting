// A bookmaker's name as a link to its football pages, wherever a price, pick or bundle names one. These are the
// bookmakers' own front doors, not the match or the bet: that needs each bookmaker's own id for the match, which
// our price feed doesn't carry (see HANDOFF.md, "Bookmaker links"). An affiliate code, once we have one, goes on
// the address here. A name not in the table (an old pick priced at Pinnacle, say) shows as plain text.
const SITES = {
  bet365: 'https://www.bet365.com/',
  williamhill: 'https://sports.williamhill.com/betting/en-gb/football',
  betfair: 'https://www.betfair.com/sport/football',
  betvictor: 'https://www.betvictor.com/en-gb/sports',
  betano: 'https://www.betano.co.uk/en-gb/sport/football',
}

export function bookmakerUrl(name) {
  const key = (name || '').toLowerCase().replace(/[^a-z0-9]/g, '')
  const site = Object.keys(SITES).find((k) => key.startsWith(k))
  return site ? SITES[site] : null
}

export default function BookLink({ name, className = '' }) {
  const url = bookmakerUrl(name)
  if (!url) return <span className={className}>{name}</span>
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      title={`Open ${name} in a new tab`}
      className={`underline decoration-ink/30 underline-offset-2 hover:text-ink hover:decoration-ink ${className}`}
    >
      {name}
    </a>
  )
}
