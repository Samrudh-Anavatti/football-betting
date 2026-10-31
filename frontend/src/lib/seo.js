// Page titles and descriptions for search engines and link previews. Plain JS (no React) because the
// Cloudflare Pages build step and the match-page function (frontend/functions) use it too.
import { pickLabel } from './format.js'

export const SITE = 'Football Predictions AI'
export const SITE_URL = 'https://football-predictions.org'
export const API_URL = 'https://api.football-predictions.org/api/v1'

const HOME_DESCRIPTION =
  'Simple, confident football picks from our team, every one on the record, plus odds and stats for every fixture.'

// Pages with fixed text. The build writes each into its own HTML file, so crawlers see it without running the app.
export const PAGES = {
  '/': {
    title: `${SITE}: expert football picks, odds and AI match analysis`,
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
    title: `Our record: every settled pick | ${SITE}`,
    description: 'Every pick we have made, won or lost, with the price taken and the profit or loss. Nothing deleted.',
  },
  '/friends': {
    title: `Football Friends | ${SITE}`,
    description: 'Football sites run by people we know and rate.',
  },
  '/privacy': {
    title: `Privacy | ${SITE}`,
    description: 'What Football Predictions AI collects (very little), the cookies it uses and how to contact us.',
  },
  '/admin': { title: `Sign in | ${SITE}`, description: HOME_DESCRIPTION, noindex: true },
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
