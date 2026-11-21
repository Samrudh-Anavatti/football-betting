"""Who gets what: every gated feature and the level it needs.

Three levels: a visitor (not signed in), an account (signed up, free) and a member (paying, or an admin). While the
paywall is off every feature sits at "account", which stands in for it; moving one behind the paywall later is a
change to its line here and nothing else. The frontend reads the answers from `/auth/me` (`access`)."""
from .models import User
from .services.billing import is_member

LEVELS = ("visitor", "account", "member")

FEATURES = {
    "all_picks": "account",  # every open pick; visitors see the top FREE_PICKS
    "ai_bets": "account",  # the AI's suggested bets on a match page (its read and probabilities stay public)
    "tonight": "account",  # tonight's bundles: the day's default bundle
    "tonight_custom": "account",  # ...and any session, matches and target (for members once the paywall opens)
    "staking": "account",  # the staking plan (for members once the paywall opens)
    "arbitrage": "account",  # the arbitrage list (for members once the paywall opens)
}


def level(user: User | None) -> str:
    if user is None:
        return "visitor"
    return "member" if is_member(user) else "account"


def can(user: User | None, feature: str) -> bool:
    return LEVELS.index(level(user)) >= LEVELS.index(FEATURES[feature])


def access_dict(user: User | None) -> dict:
    return {f: can(user, f) for f in FEATURES}
