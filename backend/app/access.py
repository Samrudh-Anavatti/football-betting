"""Who gets what: every gated feature and the level it needs.

Three levels:
* a **visitor** (not signed in) gets the home page (the three free picks and the bundle of the day), fixtures and
  results, and the basics of a match page (teams, score, line-ups);
* an **account** (signed up, free) can open every page, but several are a preview: one bundle of the day and the
  day's default Tonight bundle, the staking plan's live bundle and stake, the top `ARB_PREVIEW` arbitrages;
* a **member** (paying, or an admin) gets all of it.

Moving a feature between levels is a change to its line here and nothing else: the API enforces it
(`deps.require`), and the frontend reads the answers from `/auth/me` (`access`)."""
from .models import User
from .services.billing import is_member

LEVELS = ("visitor", "account", "member")
ARB_PREVIEW = 2  # arbitrages an account sees; members see the list

FEATURES = {
    "match_detail": "account",  # a match's prices, research and AI read (visitors: teams, score, line-ups)
    "all_picks": "account",  # every open pick; visitors see the top FREE_PICKS
    "ai_bets": "member",  # the AI's suggested bets on a match page
    "tonight": "account",  # tonight's bundles: the day's default bundle
    "tonight_custom": "member",  # ...and any session, matches and target
    "staking": "account",  # the staking plan: the live bundle and its stake
    "staking_full": "member",  # ...and the run so far
    "arbitrage": "account",  # the arbitrage list: the top ARB_PREVIEW
    "arbitrage_full": "member",  # ...and the rest
}


def level(user: User | None) -> str:
    if user is None:
        return "visitor"
    return "member" if is_member(user) else "account"


def can(user: User | None, feature: str) -> bool:
    return LEVELS.index(level(user)) >= LEVELS.index(FEATURES[feature])


def access_dict(user: User | None) -> dict:
    return {f: can(user, f) for f in FEATURES}
