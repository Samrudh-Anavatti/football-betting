"""ORM models.

Provider data (leagues, teams, fixtures, odds, match context) is a *cache* of
what the APIs returned, stamped with when we fetched it. Our own data (users,
tips, bets) is the valuable part and never gets overwritten by a sync.

All datetimes are naive UTC.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.utcnow()


# ── Provider cache ───────────────────────────────────────────────────────────


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # API-Football id
    name: Mapped[str] = mapped_column(String(80))
    country: Mapped[str] = mapped_column(String(40))
    flag: Mapped[str] = mapped_column(String(16), default="")
    logo: Mapped[str | None] = mapped_column(String(255))
    odds_key: Mapped[str] = mapped_column(String(60))
    season: Mapped[int] = mapped_column(Integer)
    fixtures_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    odds_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    standings_json: Mapped[str | None] = mapped_column(Text)
    standings_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # API-Football id
    name: Mapped[str] = mapped_column(String(80))
    logo: Mapped[str | None] = mapped_column(String(255))


class Fixture(Base):
    __tablename__ = "fixtures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # API-Football id
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    season: Mapped[int] = mapped_column(Integer)
    round: Mapped[str | None] = mapped_column(String(80))
    kickoff: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(8), default="NS")  # API-Football short code
    status_long: Mapped[str | None] = mapped_column(String(40))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    # 90-minute score (what bets settle on); null until played.
    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
    # Half-time score, for first/second-half markets.
    ht_home_goals: Mapped[int | None] = mapped_column(Integer)
    ht_away_goals: Mapped[int | None] = mapped_column(Integer)
    venue: Mapped[str | None] = mapped_column(String(120))
    odds_event_id: Mapped[str | None] = mapped_column(String(64), index=True)
    odds_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    league: Mapped[League] = relationship()
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])


class OddsSnapshot(Base):
    """One bookmaker price at one moment. Append-only: every pull adds rows, so we
    keep price history (needed later for closing-line value and line movement)."""

    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    pulled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    bookmaker_key: Mapped[str] = mapped_column(String(40))
    bookmaker: Mapped[str] = mapped_column(String(60))
    market: Mapped[str] = mapped_column(String(8))  # 1X2 | OU
    selection: Mapped[str] = mapped_column(String(8))  # home|draw|away|over|under
    line: Mapped[float | None] = mapped_column(Float)  # e.g. 2.5 for OU
    price: Mapped[float] = mapped_column(Float)  # decimal odds
    bookmaker_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (Index("ix_odds_fixture_pull", "fixture_id", "pulled_at"),)


class MarketBook(Base):
    """Every market API-Football's /odds has for a fixture, for our chosen
    bookmakers, as one JSON document (thousands of prices, so not one row each).

    Holds the latest pull only, and stops updating at kick-off, so after the match
    it is the closing book. Core markets (result, totals, BTTS) are also written
    to odds_snapshots on every pull, which keeps their price history.
    """

    __tablename__ = "market_books"

    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), default="api_football")
    pulled_at: Mapped[datetime] = mapped_column(DateTime)
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    # [{"id", "name", "bets": [{"id", "name", "values": [{"value", "odd"}]}]}], as the API sends it.
    bookmakers_json: Mapped[str] = mapped_column(Text)


class MatchContext(Base):
    """Per-fixture research bundle (H2H, form, injuries) — fetched on demand."""

    __tablename__ = "match_context"

    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), primary_key=True)
    h2h_json: Mapped[str | None] = mapped_column(Text)
    home_form_json: Mapped[str | None] = mapped_column(Text)
    away_form_json: Mapped[str | None] = mapped_column(Text)
    injuries_json: Mapped[str | None] = mapped_column(Text)
    # Pro-plan extras: API-Football's own prediction, season stats per team, line-ups.
    prediction_json: Mapped[str | None] = mapped_column(Text)
    home_stats_json: Mapped[str | None] = mapped_column(Text)
    away_stats_json: Mapped[str | None] = mapped_column(Text)
    lineups_json: Mapped[str | None] = mapped_column(Text)
    lineups_fetched_at: Mapped[datetime | None] = mapped_column(DateTime)
    errors_json: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ── Integration bookkeeping ──────────────────────────────────────────────────


class ProviderQuota(Base):
    """Last known allowance per provider, refreshed from response headers on
    every call (and on demand via each provider's free status endpoint)."""

    __tablename__ = "provider_quota"

    provider: Mapped[str] = mapped_column(String(20), primary_key=True)
    used: Mapped[int | None] = mapped_column(Integer)
    remaining: Mapped[int | None] = mapped_column(Integer)
    limit: Mapped[int | None] = mapped_column(Integer)
    plan: Mapped[str | None] = mapped_column(String(60))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


class SyncRun(Base):
    """One press of a sync button: what ran, what it cost, what happened."""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))  # api_football | odds_api | claude
    # fixtures | odds | context | match_odds | markets | match_markets | lineups | analysis | chat
    kind: Mapped[str] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(255), default="")  # human description
    status: Mapped[str] = mapped_column(String(10), default="running")  # running|ok|partial|error
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    requests_made: Mapped[int] = mapped_column(Integer, default=0)
    credits_used: Mapped[int] = mapped_column(Integer, default=0)
    items: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


# ── Our data ─────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    display_name: Mapped[str] = mapped_column(String(60))
    password_hash: Mapped[str] = mapped_column(String(100))
    starting_bankroll: Mapped[float] = mapped_column(Float, default=1000.0)


class Tip(Base):
    """A recommendation. Ivo's are published; the AI's are private (published=False)
    but settle the same way, so both build a track record. Locked at kick-off.

    market/selection are either our short codes (1X2/OU/BTTS + home/over/yes...)
    or, for anything else on the board, API-Football's names ("Double Chance" /
    "Home/Draw"), with market_id set to its bet id.
    """

    __tablename__ = "tips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(8), default="ivo")  # ivo | ai
    ai_prediction_id: Mapped[int | None] = mapped_column(Integer)
    market_id: Mapped[int | None] = mapped_column(Integer)
    market: Mapped[str] = mapped_column(String(80))
    selection: Mapped[str] = mapped_column(String(120))
    line: Mapped[float | None] = mapped_column(Float)
    odds: Mapped[float] = mapped_column(Float)
    bookmaker: Mapped[str | None] = mapped_column(String(60))
    stake_units: Mapped[float] = mapped_column(Float, default=1.0)
    confidence: Mapped[int] = mapped_column(Integer, default=3)  # 1–5
    reasoning: Mapped[str | None] = mapped_column(Text)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(8), default="pending")  # pending|won|lost|void
    profit_units: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime)

    fixture: Mapped[Fixture] = relationship()
    author: Mapped[User] = relationship()


class Bet(Base):
    """A virtual-money bet in someone's tracked account (often following a tip)."""

    __tablename__ = "bets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tip_id: Mapped[int | None] = mapped_column(ForeignKey("tips.id"))
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    market_id: Mapped[int | None] = mapped_column(Integer)
    market: Mapped[str] = mapped_column(String(80))
    selection: Mapped[str] = mapped_column(String(120))
    line: Mapped[float | None] = mapped_column(Float)
    odds: Mapped[float] = mapped_column(Float)
    bookmaker: Mapped[str | None] = mapped_column(String(60))
    stake: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(8), default="pending")
    profit: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime)

    fixture: Mapped[Fixture] = relationship()
    user: Mapped[User] = relationship()


# ── AI analysis ──────────────────────────────────────────────────────────────


class AiThread(Base):
    """One conversation with Claude about one fixture. The first turn sends the
    match bundle and asks for an analysis; later turns are follow-up chat.
    "Start fresh" opens a new thread with a newly built bundle, so a thread's
    context never changes under it (which keeps the prompt cache valid)."""

    __tablename__ = "ai_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    model: Mapped[str] = mapped_column(String(40))
    effort: Mapped[str] = mapped_column(String(10))
    prompt_version: Mapped[str] = mapped_column(String(10))
    bundle_json: Mapped[str] = mapped_column(Text)  # exactly what Claude was sent
    bundle_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AiMessage(Base):
    """One API message in a thread, stored exactly as sent/received (content
    blocks as JSON, thinking blocks included) so history replays unchanged."""

    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("ai_threads.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    content_json: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(40))  # who typed it (user turns)
    stop_reason: Mapped[str | None] = mapped_column(String(20))
    # Assistant turns: what that API call used and cost.
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AiPrediction(Base):
    """A structured analysis Claude recorded (through its record_analysis tool).
    The latest one before kick-off is the AI's call for the match."""

    __tablename__ = "ai_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("ai_threads.id"), index=True)
    tool_use_id: Mapped[str | None] = mapped_column(String(64))
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    model: Mapped[str] = mapped_column(String(40))
    prompt_version: Mapped[str] = mapped_column(String(10))
    analysis_json: Mapped[str] = mapped_column(Text)
    # Margin-free bookmaker probabilities at the time, to score against later.
    market_probs_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
