"""Claude match analysis: one conversation (thread) per fixture.

The first turn sends the match bundle and asks for an analysis, which Claude
records through the `record_analysis` tool (strict schema, so the arguments
always parse). Follow-up chat reuses the thread: the full history is resent
each turn, unchanged and append-only, and prompt caching makes the repeated
bundle cheap. A recorded analysis becomes an AiPrediction plus private AI tips
that settle like Ivo's, so the AI earns its own track record.

Calls run in a background thread as a SyncRun (provider "claude"), the same
pattern as the data syncs, so the UI shows progress and the cost lands in history.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..models import AiMessage, AiPrediction, AiThread, Fixture, Tip, User
from ..services.markets import market_probs, parse_value, to_code
from ..services.board import match_board
from .bundle import build_bundle, find_selection, serialise
from .client import cost_usd, make_client

log = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
MAX_TOOL_ROUNDS = 3

FIRST_TURN = (
    "Analyse this match. Work out your probabilities, compare them with the prices across all the markets, "
    "record your analysis with record_analysis, then give Ivo and Sam a short summary."
)

_PROB = {"type": "number", "description": "0 to 1"}
RECORD_ANALYSIS = {
    "name": "record_analysis",
    "description": (
        "Record your structured analysis of this match: your probabilities, the bets you suggest (if any) and "
        "why. Call it once per full analysis, and again whenever your view changes; the latest call before "
        "kick-off is the one your track record is judged on."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "probabilities", "suggested_bets", "key_factors", "data_gaps", "no_bet"],
        "properties": {
            "summary": {"type": "string", "description": "Two to four sentences: your overall read of the match."},
            "probabilities": {
                "type": "object",
                "additionalProperties": False,
                "required": ["home_win", "draw", "away_win", "over_2_5_goals", "both_teams_score"],
                "properties": {"home_win": _PROB, "draw": _PROB, "away_win": _PROB,
                               "over_2_5_goals": _PROB, "both_teams_score": _PROB},
            },
            "suggested_bets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["market_id", "market", "value", "your_probability", "min_odds", "stake_units",
                                 "confidence", "reasoning"],
                    "properties": {
                        "market_id": {"type": "integer", "description": "market_id from the bundle"},
                        "market": {"type": "string", "description": "market name from the bundle"},
                        "value": {"type": "string", "description": "selection value exactly as in the bundle"},
                        "your_probability": _PROB,
                        "min_odds": {"type": "number", "description": "lowest decimal price you'd still take"},
                        "stake_units": {"type": "number", "description": "0.5 to 3"},
                        "confidence": {"type": "integer", "description": "1 to 5"},
                        "reasoning": {"type": "string"},
                    },
                },
            },
            "key_factors": {"type": "array", "items": {"type": "string"}},
            "data_gaps": {"type": "array", "items": {"type": "string"},
                          "description": "Missing information that limits this analysis"},
            "no_bet": {"type": "boolean", "description": "true when nothing offers enough value"},
        },
    },
}


class SuggestedBet(BaseModel):
    market_id: int
    market: str
    value: str
    your_probability: float = Field(ge=0, le=1)
    min_odds: float = Field(gt=1)
    stake_units: float
    confidence: int
    reasoning: str


class Analysis(BaseModel):
    summary: str
    probabilities: dict[str, float]
    suggested_bets: list[SuggestedBet]
    key_factors: list[str]
    data_gaps: list[str]
    no_bet: bool


class AiError(Exception):
    pass


# ── Budget ───────────────────────────────────────────────────────────────────


def month_spend(db: Session) -> float:
    start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return round(db.scalar(select(func.coalesce(func.sum(AiMessage.cost_usd), 0.0))
                           .where(AiMessage.created_at >= start)) or 0.0, 4)


def estimate_cost(bundle_text: str) -> float:
    """Rough first-turn cost: bundle + prompt in, a few thousand tokens out."""
    inp, out, _, _ = config.AI_PRICES.get(config.AI_MODEL, config.AI_PRICES["claude-sonnet-5-5"])
    tokens_in = len(bundle_text) / 3.2 + len(SYSTEM_PROMPT) / 4 + 1500
    return round((tokens_in * 1.3 * inp + 5000 * out) / 1_000_000, 3)  # ~2 calls (tool round trip)


# ── Threads ──────────────────────────────────────────────────────────────────


def new_thread(db: Session, fx: Fixture, user: User) -> AiThread:
    bundle = build_bundle(db, fx)
    text, digest = serialise(bundle)
    thread = AiThread(fixture_id=fx.id, model=config.AI_MODEL, effort=config.AI_EFFORT,
                      prompt_version=PROMPT_VERSION, bundle_json=text, bundle_hash=digest,
                      created_by=user.display_name)
    db.add(thread)
    db.flush()
    db.add(AiMessage(thread_id=thread.id, role="user", author=user.display_name, content_json=json.dumps([
        {"type": "text", "text": f"<match_bundle>\n{text}\n</match_bundle>"},
        {"type": "text", "text": FIRST_TURN},
    ])))
    db.commit()
    return thread


def add_user_message(db: Session, thread: AiThread, user: User, text: str) -> None:
    db.add(AiMessage(thread_id=thread.id, role="user", author=user.display_name,
                     content_json=json.dumps([{"type": "text", "text": text}])))
    db.commit()


def _history(db: Session, thread: AiThread) -> list[dict]:
    """The conversation as API messages, exactly as stored (append-only)."""
    rows = db.scalars(select(AiMessage).where(AiMessage.thread_id == thread.id).order_by(AiMessage.id))
    return [{"role": m.role, "content": json.loads(m.content_json)} for m in rows]


# ── The conversation loop ────────────────────────────────────────────────────


def _record(db: Session, thread: AiThread, fx: Fixture, user_id: int, raw: dict, tool_use_id: str) -> tuple[AiPrediction | None, str]:
    """Store a record_analysis call. Returns (prediction, tool_result text)."""
    try:
        a = Analysis.model_validate(raw)
    except ValidationError as e:
        return None, f"Not recorded: the input didn't validate ({e.errors()[0]['msg']}). Please call it again."
    if fx.kickoff <= datetime.utcnow():
        return None, "Not recorded: the match has kicked off."

    bundle = json.loads(thread.bundle_json)
    board = match_board(db, fx.id)
    pred = AiPrediction(thread_id=thread.id, tool_use_id=tool_use_id, fixture_id=fx.id, model=thread.model,
                        prompt_version=thread.prompt_version, analysis_json=a.model_dump_json(),
                        market_probs_json=json.dumps(market_probs(board["markets"])))
    db.add(pred)
    db.flush()

    # The latest analysis replaces earlier AI tips on this match (still private and pre-kick-off).
    for old in db.scalars(select(Tip).where(Tip.fixture_id == fx.id, Tip.source == "ai", Tip.status == "pending")):
        db.delete(old)

    notes, placed = [], 0
    for b in a.suggested_bets:
        sel = find_selection(bundle, b.market_id, b.value)
        if sel is None:
            notes.append(f"'{b.market} / {b.value}' isn't in the bundle's prices, so it wasn't tracked")
            continue
        if sel["best"] < b.min_odds:
            notes.append(f"'{b.market} / {b.value}' is {sel['best']} now, below your minimum {b.min_odds}: not tracked")
            continue
        market, selection, line, market_id = b.market, b.value, None, b.market_id
        if code := to_code(b.market_id, b.value):
            market, selection, line = code
            market_id = None
        else:
            line = parse_value(b.value)[1]
        db.add(Tip(fixture_id=fx.id, author_id=user_id, source="ai", ai_prediction_id=pred.id, published=False,
                   market_id=market_id, market=market, selection=selection, line=line, odds=sel["best"],
                   bookmaker=sel["at"], stake_units=min(max(b.stake_units, 0.5), 3),
                   confidence=min(max(b.confidence, 1), 5), reasoning=b.reasoning))
        placed += 1
    db.commit()
    msg = f"Recorded as analysis #{pred.id}; {placed} bet{'s' * (placed != 1)} tracked at the best current price."
    if notes:
        msg += " " + "; ".join(notes) + "."
    return pred, msg


def run_turn(db: Session, thread: AiThread, user_id: int) -> dict:
    """Send the thread to Claude and handle tool calls until it finishes its reply."""
    client = make_client()
    fx = db.get(Fixture, thread.fixture_id)
    recorded, cost = [], 0.0
    for _ in range(MAX_TOOL_ROUNDS):
        try:
            resp = client.messages.create(
                model=thread.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=[RECORD_ANALYSIS],
                messages=_history(db, thread),
                thinking={"type": "adaptive"},
                output_config={"effort": thread.effort},
                cache_control={"type": "ephemeral"},
            )
        except anthropic.RateLimitError as e:
            raise AiError("Claude is rate-limited right now; try again in a minute") from e
        except anthropic.APIStatusError as e:
            raise AiError(f"Claude API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AiError(f"Couldn't reach Claude: {e}") from e

        u = resp.usage
        c = cost_usd(thread.model, u)
        cost += c
        db.add(AiMessage(
            thread_id=thread.id, role="assistant", stop_reason=resp.stop_reason,
            content_json=json.dumps([b.to_dict() for b in resp.content]),
            input_tokens=u.input_tokens or 0, output_tokens=u.output_tokens or 0,
            cache_read_tokens=u.cache_read_input_tokens or 0, cache_write_tokens=u.cache_creation_input_tokens or 0,
            cost_usd=c,
        ))
        db.commit()

        if resp.stop_reason == "refusal":
            cat = getattr(resp.stop_details, "category", None) if resp.stop_details else None
            raise AiError(f"Claude declined to answer (category: {cat or 'unspecified'})")
        if resp.stop_reason == "max_tokens":
            raise AiError("Claude's reply hit the length limit")
        if resp.stop_reason != "tool_use":
            break

        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            if block.name == "record_analysis":
                pred, text = _record(db, thread, fx, user_id, block.input, block.id)
                if pred:
                    recorded.append(pred.id)
            else:
                text = f"Unknown tool {block.name}"
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": text})
        db.add(AiMessage(thread_id=thread.id, role="user", content_json=json.dumps(results)))
        db.commit()
    return {"recorded": recorded, "cost_usd": round(cost, 6)}


def job_turn(db: Session, run, thread_id: int, user_id: int, expect_analysis: bool) -> None:
    """SyncRun job: one user turn through to Claude's final reply."""
    thread = db.get(AiThread, thread_id)
    try:
        out = run_turn(db, thread, user_id)
        run.items = len(out["recorded"])
        run.status = "ok"
        if expect_analysis and not out["recorded"]:
            run.status, run.message = "partial", "Claude replied but didn't record a structured analysis"
        run.details_json = json.dumps({"thread_id": thread.id, **out})
    except AiError as e:
        run.status, run.message = "error", str(e)
        run.details_json = json.dumps({"thread_id": thread.id})
    run.progress = 1
    run.finished_at = datetime.utcnow()
    db.commit()


# ── Views ────────────────────────────────────────────────────────────────────


def thread_view(db: Session, thread: AiThread) -> dict:
    """The thread as the UI shows it: typed messages, Claude's text, analyses."""
    preds = {p.id: p for p in db.scalars(select(AiPrediction).where(AiPrediction.thread_id == thread.id))}
    tips = list(db.scalars(select(Tip).where(Tip.ai_prediction_id.in_(preds.keys())))) if preds else []
    by_tool_use = {p.tool_use_id: p.id for p in preds.values()}
    msgs, spent = [], 0.0
    for m in db.scalars(select(AiMessage).where(AiMessage.thread_id == thread.id).order_by(AiMessage.id)):
        spent += m.cost_usd or 0
        blocks = json.loads(m.content_json)
        if m.role == "user":
            typed = [b["text"] for b in blocks if b.get("type") == "text" and not b["text"].startswith("<match_bundle>")]
            if typed and typed[0] != FIRST_TURN:
                msgs.append({"id": m.id, "role": "user", "author": m.author, "text": "\n".join(typed),
                             "created_at": m.created_at})
            continue
        text = "\n\n".join(b["text"] for b in blocks if b.get("type") == "text" and b.get("text"))
        recorded = [b for b in blocks if b.get("type") == "tool_use" and b.get("name") == "record_analysis"]
        entry = {"id": m.id, "role": "assistant", "text": text, "created_at": m.created_at,
                 "stop_reason": m.stop_reason}
        ids = [by_tool_use[b["id"]] for b in recorded if b.get("id") in by_tool_use]
        if ids:
            entry["prediction_id"] = ids[-1]
        if text or recorded:
            msgs.append(entry)
    return {
        "id": thread.id, "fixture_id": thread.fixture_id, "model": thread.model, "effort": thread.effort,
        "prompt_version": thread.prompt_version, "created_by": thread.created_by, "created_at": thread.created_at,
        "bundle_built_at": json.loads(thread.bundle_json).get("bundle_built_at"),
        "cost_usd": round(spent, 4),
        "messages": msgs,
        "predictions": [
            {"id": p.id, "created_at": p.created_at, "analysis": json.loads(p.analysis_json),
             "market_probs": json.loads(p.market_probs_json) if p.market_probs_json else None,
             "tips": [t.id for t in tips if t.ai_prediction_id == p.id]}
            for p in preds.values()
        ],
    }
