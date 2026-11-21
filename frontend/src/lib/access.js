// Who gets what, as the API decided it (backend/app/access.py): `/auth/me` carries `access`, one yes/no per gated
// feature. A visitor (nobody signed in) has none of them.
import { useLocation } from 'react-router-dom'
import { useAuth } from './auth.jsx'

export function useCan(feature) {
  const { user } = useAuth()
  return !!user?.access?.[feature]
}

// The sign-up page, set to come back to the page the visitor is on.
export function useJoinPath() {
  const { pathname } = useLocation()
  return `/signup?next=${encodeURIComponent(pathname)}`
}

// What a free account adds, in the order the sign-up page and the home page list it.
export const ACCOUNT_PERKS = [
  ["Tonight's bundles", "Tick the matches you're watching and the AI builds up to three bundles from its surest calls."],
  ['Every pick', 'All of our open picks each day, not just the top three, with the price and the thinking.'],
  ["The AI's suggested bets", 'On every match page, with the price to take and how confident it is.'],
  ['The staking plan', 'Our picks bundled at about 6.00, each stake worked out, scaled to your own.'],
  ['Arbitrage finder', 'Markets where the best prices across five bookmakers add up to a profit whatever happens.'],
]
