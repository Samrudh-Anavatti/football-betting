// Staking plan maths, matching backend/app/services/staking.py: the stake for a bundle is whatever makes a win recover
// the run's losses plus the target profit, (losses + base × (target − 1)) ÷ (odds − 1).

export const targetProfit = (plan) => plan.base_stake * (plan.target_odds - 1)

export const stakeFor = (plan, losses, odds) => Math.round(((losses + targetProfit(plan)) / (odds - 1)) * 100) / 100

export const combinedOdds = (tips) => Math.round(tips.reduce((acc, t) => acc * t.odds, 1) * 100) / 100

// The bets of a losing run at the target odds, until the bank can't cover the next one.
export function ladder(plan) {
  const rows = []
  let lost = 0
  for (let step = 1; step <= 30; step++) {
    const stake = stakeFor(plan, lost, plan.target_odds)
    rows.push({ step, stake, lostBefore: lost, affordable: lost + stake <= plan.bank })
    if (lost + stake > plan.bank) break
    lost += stake
  }
  return rows
}

// Chance a bundle wins if each pick lands at `hitRate`, and of losing `n` bundles in a row from the start of a run.
export const bundleWinChance = (hitRate, legs) => hitRate ** legs
export const streakChance = (bundleWin, n) => (1 - bundleWin) ** n
