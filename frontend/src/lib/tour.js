// Mr Predictions' welcome. For a visitor it is the way through the site: the record (why trust us), today's picks,
// tonight's bundles, then the Join button. On other pages he points out one thing, and where something is locked
// he says what an account opens. Someone who has just joined gets a short second tour of what they now have.
// Each step names a `data-tour` anchor in the page; steps whose anchor isn't on the page are skipped, so a page
// with no open picks, say, just has fewer stops. Images: `/mr-predictions.jpg` (desk shot) and
// `/mr-predictions-face.jpg` (phones); a step can name its own `image` once there are more poses.

export const PORTRAIT = '/mr-predictions.jpg'
export const FACE = '/mr-predictions-face.jpg'

// `visitor: true` steps only show to someone not signed in (their anchors are the locked cards and Join button,
// which a signed-in page doesn't have anyway; the flag just keeps the intent readable).
const STEPS = {
  home: [
    {
      target: 'record',
      text: "Welcome, I'm Mr Predictions. Start here: our record. Our picks from the last two weeks, settled against the final score, with the profit they made. The losers count too.",
    },
    {
      target: 'picks',
      text: "Today's picks. Each goes up before kick-off with the price we took and the thinking behind it. Open any match for the odds board and the AI's read on it.",
    },
    {
      target: 'daily',
      text: "The bundle of the day: one bet a day, chosen by the AI from every match, with the reason for each leg and what to stake. It's free to see, every day.",
    },
    {
      target: 'tonight',
      text: "Watching a few games? Tonight's bundles turns the AI's surest calls on them into two or three bets to cheer for. Our staking plan and the arbitrage finder sit alongside.",
    },
    {
      target: 'nav-join',
      visitor: true,
      text: 'The bundles, every pick and the tools are free with an account: an email and a password, no card. Join here whenever you like.',
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
      text: "Our record for the last two weeks, newest first. Every pick settled in that time, won or lost, with the price we took.",
    },
  ],
  staking: [
    {
      target: 'staking',
      text: 'Our picks combined into one bet at about 6.00. After a loss the stake rises just enough that the next win pays the run back and still makes the profit. Scale it to your own stake.',
    },
    {
      target: 'locked',
      visitor: true,
      text: "What's behind me is a sample. Join free and this page shows the live bundle, the stakes and every result.",
    },
  ],
  match: [
    {
      target: 'prices',
      text: "The best price for every market across five bookmakers, with the fair price worked out from them. Above it, the AI's analysis; below, form, injuries and line-ups.",
    },
    {
      target: 'locked',
      visitor: true,
      text: "There's more on this match for accounts: our pick or the AI's suggested bets, with the price to take. It's free to join.",
    },
  ],
  membership: [
    {
      target: 'join',
      text: 'Our picks and match analysis stay free. Membership adds the staking plan: monthly, cancel any time.',
    },
  ],
  tonight: [
    {
      target: 'tonight',
      text: "Pick the session you're sitting down for, untick anything you won't watch, and up to three bundles appear. Tap Why on any leg for the AI's reason. Every bundle shown lands on the record, hit or miss.",
    },
    {
      target: 'locked',
      visitor: true,
      text: "These are tonight's matches. Join free and the bundles for them appear right here.",
    },
  ],
  arbitrage: [
    {
      target: 'arbitrage',
      text: 'Now and then the best prices at different bookmakers add up to a profit whichever way the match goes. We scan every market for those and work out the stakes.',
    },
    {
      target: 'locked',
      visitor: true,
      text: 'The live list is free with an account. Join and it opens here.',
    },
  ],
}

// Straight after signing up, wherever they land: what the account opened. All three anchors are in the header.
const JOINED = [
  {
    target: 'nav-bundles',
    text: "You're in. Tonight's bundles and our staking plan are under Bundles: tick the matches you're watching and the slips appear.",
  },
  {
    target: 'nav-arbitrage',
    text: 'Arbitrage lists the markets where the best prices across bookmakers add up to a profit, with the stakes worked out.',
  },
  {
    target: 'nav-account',
    text: "Every pick and the AI's suggested bets are open on every match now. Your account lives up here.",
  },
]

const PENDING = 'tour:joined'

// Sign-up calls this; the next page shows the joined tour once.
export function queueWelcome() {
  try {
    sessionStorage.setItem(PENDING, '1')
  } catch {
    /* private mode: no second tour */
  }
}

// The joined tour if one is waiting. It stays waiting until `clearWelcome` (called when it ends), so a page that
// re-renders before it shows doesn't lose it.
export function pendingWelcome() {
  try {
    return sessionStorage.getItem(PENDING) === '1' ? JOINED : null
  } catch {
    return null
  }
}

export function clearWelcome() {
  try {
    sessionStorage.removeItem(PENDING)
  } catch {
    /* nothing to clear */
  }
}

// Which tour a path gets: match pages share one, the home page is 'home', the rest go by their first segment.
export function tourKey(pathname) {
  if (pathname === '/') return 'home'
  const first = pathname.split('/')[1]
  return first === 'match' ? 'match' : first
}

export const stepsFor = (pathname) => STEPS[tourKey(pathname)] || []
