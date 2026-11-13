// Mr Predictions' welcome: on each page he points out one thing (three on the home page), then gets out of the
// way. Each step names a `data-tour` anchor in the page; steps whose anchor isn't on the page are skipped, so a page
// with no open picks, say, just has fewer stops. Images: `/mr-predictions.jpg` (desk shot) and
// `/mr-predictions-face.jpg` (phones); a step can name its own `image` once Ivo has more poses.

export const PORTRAIT = '/mr-predictions.jpg'
export const FACE = '/mr-predictions-face.jpg'

const STEPS = {
  home: [
    {
      target: 'record',
      text: "Welcome, I'm Mr Predictions. This is our record: every pick we've made, settled against the final score, and the profit so far up top. Nothing gets hidden.",
    },
    {
      target: 'picks',
      text: "Today's picks live here. Each one goes up before kick-off with the price we took and the thinking behind it. Open a match for the odds board and the AI's read on it.",
    },
    {
      target: 'nav-staking',
      text: 'Members follow our staking plan: the picks bundled at about 6.00, with stakes that win back every loss. Have a look under Staking.',
    },
  ],
  fixtures: [
    {
      target: 'fixtures',
      text: 'Every upcoming match across 40-odd leagues. Tap one for the best prices from five bookmakers, form, injuries, line-ups and an AI analysis.',
    },
  ],
  results: [
    {
      target: 'fixtures',
      text: 'Final scores, and how our picks and the AI did on each match.',
    },
  ],
  history: [
    {
      target: 'history',
      text: "Our full record, newest first. Every settled pick, won or lost, with the price we took. Nothing's ever deleted.",
    },
  ],
  staking: [
    {
      target: 'staking',
      text: 'Our picks combined into one bet at about 6.00. After a loss the stake rises just enough that the next win pays the run back and still makes the profit. Scale it to your own stake.',
    },
  ],
  match: [
    {
      target: 'prices',
      text: "The best price for every market across five bookmakers, with the fair price worked out from them. Above it, the AI's analysis; below, form, injuries and line-ups.",
    },
  ],
  membership: [
    {
      target: 'join',
      text: 'Our picks and match analysis stay free. Membership adds the staking plan: monthly, cancel any time.',
    },
  ],
  'ai-lab': [
    {
      target: 'ai-lab',
      text: "The AI's own staking test, built from its surest legs, and an arbitrage scanner over the prices we already pull.",
    },
  ],
}

// Which tour a path gets: match pages share one, the home page is 'home', the rest go by their first segment.
export function tourKey(pathname) {
  if (pathname === '/') return 'home'
  const first = pathname.split('/')[1]
  return first === 'match' ? 'match' : first
}

export const stepsFor = (pathname) => STEPS[tourKey(pathname)] || []
