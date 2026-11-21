// Page titles and descriptions for search engines and link previews. Plain JS (no React) because the
// Cloudflare Pages build step and the match-page function (frontend/functions) use it too.
import { pickLabel } from './format.js'

export const SITE = 'Football Predictions AI'
export const SITE_URL = 'https://football-predictions.org'
export const API_URL = 'https://api.football-predictions.org/api/v1'

const HOME_DESCRIPTION =
  "Football picks from our team and bundles built by AI for the matches you're watching, every one on the record, plus odds, stats and analysis for every fixture."

// Pages with fixed text. The build writes each into its own HTML file, so crawlers see it without running the app.
export const PAGES = {
  '/': {
    title: `${SITE}: football picks, AI bundles and odds for tonight's matches`,
    description: HOME_DESCRIPTION,
  },
  '/fixtures': {
    title: `Football fixtures, odds and predictions | ${SITE}`,
    description:
      'Upcoming matches across 40+ leagues with the best odds from five bookmakers, form, injuries, line-ups and AI match analysis.',
  },
  '/results': {
    title: `Football results | ${SITE}`,
    description: 'Recent football results across 40+ leagues, with our picks and the AI analysis for each match.',
  },
  '/history': {
    title: `Our record: the last two weeks of picks | ${SITE}`,
    description: 'Our picks from the last two weeks, won or lost, with the price taken and the profit or loss.',
  },
  '/staking': {
    title: `Staking plan: our picks in bundles at about 6.00 | ${SITE}`,
    description:
      "Our picks combined into bets at around 6.00, with each stake worked out so a win pays the run back. Follow the live bundle and the current run.",
  },
  '/membership': {
    title: `Membership | ${SITE}`,
    description: 'Membership of Football Predictions AI: monthly, cancel any time.',
    noindex: true, // until it opens
  },
  '/terms': {
    title: `Terms | ${SITE}`,
    description: 'The terms for using Football Predictions AI and paying for membership.',
  },
  '/friends': {
    title: `Football Friends | ${SITE}`,
    description: 'Football sites run by people we know and rate.',
  },
  '/privacy': {
    title: `Privacy | ${SITE}`,
    description: 'What Football Predictions AI collects (very little), the cookies it uses and how to contact us.',
  },
  '/admin': { title: `Admin | ${SITE}`, description: HOME_DESCRIPTION, noindex: true },
  '/login': { title: `Sign in | ${SITE}`, description: HOME_DESCRIPTION, noindex: true },
  '/signup': { title: `Join free | ${SITE}`, description: HOME_DESCRIPTION, noindex: true },
  '/forgot': { title: `Reset your password | ${SITE}`, description: HOME_DESCRIPTION, noindex: true },
  '/reset': { title: `Choose a new password | ${SITE}`, description: HOME_DESCRIPTION, noindex: true },
  '/tonight': {
    title: `Tonight's bundles: AI picks for the matches you're watching | ${SITE}`,
    description:
      "Tick the matches you're sitting down for and the AI builds up to three bundles from its surest calls on them, at about 3.00, 6.00 or 10.00. Free with an account.",
  },
  '/arbitrage': {
    title: `Football arbitrage finder: prices that add up to a profit | ${SITE}`,
    description:
      'Markets where the best prices across five bookmakers add up to a profit whatever the result, with the stake for each side. Free with an account.',
  },
  '/account': { title: `Your account | ${SITE}`, description: HOME_DESCRIPTION, noindex: true },
}

const FINISHED = ['FT', 'AET', 'PEN']

// UK dates whatever the reader's or the server's time zone, so the app and the function agree.
const ukDate = (iso) =>
  new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Europe/London' })

// A match page, from GET /matches/{id}/meta (or the full match, which has the same fixture and tips).
export function matchMeta(fixture, tips = []) {
  const { home, away, league } = fixture
  const date = ukDate(fixture.kickoff)
  if (FINISHED.includes(fixture.status) && fixture.home_goals != null) {
    const score = `${home.name} ${fixture.home_goals}–${fixture.away_goals} ${away.name}`
    return {
      title: `${score}: result, odds and our picks | ${SITE}`,
      description: `${score}, ${league.name}, ${date}. Our picks for the match, the closing odds and the pre-match AI analysis.`,
    }
  }
  const picks = tips.map((t) => `${pickLabel(t, fixture)} at ${Number(t.odds).toFixed(2)}`)
  const lead = picks.length
    ? `Our pick${picks.length > 1 ? 's' : ''}: ${picks.join('; ')}.`
    : 'Our team and the AI weigh up the match.'
  return {
    title: `${home.name} vs ${away.name} prediction, odds & tips, ${date} | ${SITE}`,
    description: `${home.name} vs ${away.name}, ${league.name}, ${date}. ${lead} Best odds from five bookmakers, form, injuries and line-ups.`,
  }
}

export const canonical = (path) => SITE_URL + (path === '/' ? '/' : path)

// Letters that don't decompose into a plain one plus an accent.
const LETTERS = { ı: 'i', ø: 'o', æ: 'ae', œ: 'oe', ß: 'ss', ł: 'l', đ: 'd', þ: 'th' }

// "Atlético Madrid" -> "atletico-madrid", "Kasımpaşa" -> "kasimpasa"
const slug = (name) =>
  name
    .toLowerCase()
    .replace(/[ıøæœßłđþ]/g, (c) => LETTERS[c])
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')

// A match's address: the teams for search engines and people, the id at the end for us
// (/match/udinese-vs-as-roma-1550186). Any other spelling of it redirects here.
export function matchPath(fixture) {
  const teams = fixture.home?.name && fixture.away?.name ? `${slug(fixture.home.name)}-vs-${slug(fixture.away.name)}-` : ''
  return `/match/${teams}${fixture.id}`
}

// The id from the last part of a match address; also takes the old plain-id form (/match/1550186).
export const matchIdFrom = (param) => param.match(/(?:^|-)(\d+)$/)?.[1] ?? null
