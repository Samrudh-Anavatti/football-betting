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

// What a free account adds, in the order the sign-up page lists it.
export const ACCOUNT_PERKS = [
  ['Every pick', 'All of our open picks each day, not just the top three, with the price and the thinking.'],
  ['Every match page', "Prices from five bookmakers across every market, form, head-to-head, injuries and the AI's read."],
  ['Our record', 'Every pick from the last two weeks, won or lost, at the price we took.'],
  ['A bundle for tonight', "The AI's bundle of the day, and its pick of bundle for tonight's matches."],
  ['A look at the member tools', "The staking plan's live bundle and stake, and the best two arbitrages open right now."],
]

// What membership adds on top of a free account, in the order the membership page lists it.
export const MEMBER_PERKS = [
  ['Your own bundles', "Tick the matches you're watching, choose Safer, Standard or Big night, and get up to three bundles."],
  ["The AI's suggested bets", 'On every match page: the selection, the price to take, the stake and how confident it is.'],
  ['The full staking plan', 'Every bundle in the run so far, won or lost, and how the last run ended.'],
  ['Every arbitrage', 'The whole list, not just the top two, with the stake to put on each side.'],
]
