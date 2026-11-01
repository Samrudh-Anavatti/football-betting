// Made-up staking data for the blurred preview non-members see. Never real picks: a CSS blur only hides what the
// browser already has, so the real plan isn't sent to anyone who can't see it.
const day = (n, hour = 15) => {
  const d = new Date()
  d.setDate(d.getDate() + n)
  d.setHours(hour, 0, 0, 0)
  return d.toISOString()
}

const team = (name) => ({ name, logo: null })
const league = { name: 'League', logo: null, flag: '' }

let id = 0
function leg(home, away, selection, odds, status = 'pending', kickoff = day(1)) {
  id += 1
  const fixture = { id, home: team(home), away: team(away), league, kickoff, home_goals: null, away_goals: null }
  return { tip_id: id, odds, tip: { id, market: '1X2', selection, odds, status, fixture } }
}

function bundle(run, step, status, odds, stake, legs, daysAgo) {
  const profit = status === 'won' ? Math.round(stake * (odds - 1) * 100) / 100 : status === 'lost' ? -stake : 0
  return { id: run * 10 + step, run, step, status, odds, stake, profit, returns: stake * odds, legs,
    created_at: day(-daysAgo), settled_at: day(-daysAgo + 1) }
}

const past = (status) => [
  leg('Northbridge', 'Easton Town', 'home', 1.72, status, day(-3)),
  leg('Harbour City', 'Millfield', 'away', 1.85, 'won', day(-3)),
  leg('Westvale', 'Ashford Rovers', 'home', 1.9, 'won', day(-3)),
]

export const SAMPLE_PLAN = {
  plan: { base_stake: 6, target_odds: 6, bank: 150, target_profit: 30, multiplier: 1.2, survivable_losses: 9 },
  run: { number: 4, step: 2, losses: 6, next_stake: 7.2 },
  current: bundle(4, 2, 'pending', 6.04, 7.16, [
    leg('Kingsport United', 'Redcliffe', 'home', 1.78),
    leg('Ashford Rovers', 'Southgate', 'away', 1.95),
    leg('Millfield', 'Northbridge', 'home', 1.74),
  ], 0),
  history: [
    bundle(4, 1, 'lost', 6.05, 6, past('lost'), 3),
    bundle(3, 2, 'won', 5.98, 7.22, past('won'), 6),
    bundle(3, 1, 'lost', 6.1, 6, past('lost'), 9),
    bundle(2, 1, 'won', 6.02, 6, past('won'), 12),
    bundle(1, 3, 'won', 6.12, 8.52, past('won'), 15),
    bundle(1, 2, 'lost', 5.9, 7.2, past('lost'), 18),
    bundle(1, 1, 'lost', 6.0, 6, past('lost'), 21),
  ],
  stats: { bundles: 7, won: 3, lost: 4, runs_completed: 3, profit: 84, bank_now: 234, longest_losing_streak: 2 },
}
