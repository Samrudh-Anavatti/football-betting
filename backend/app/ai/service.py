"""AI match analysis (GPT-5.6 Luna, Responses API): one conversation per fixture.

The first turn sends the match bundle and asks for an analysis, which the model
records through the `record_analysis` function (strict schema, so the arguments
always parse). Follow-up chat reuses the thread: the full item history is resent
each turn, unchanged and append-only (reasoning items travel as encrypted
content, so nothing is stored on Azure: store=False), and automatic prompt
caching makes the repeated bundle cheap. A recorded analysis becomes an
AiPrediction plus private AI tips that settle like Ivo's, so the AI earns its
own track record.

Calls run in a background thread as a SyncRun (provider "claude", kept as the
name for the AI runs), the same pattern as the data syncs, so the UI shows
progress and the cost lands in history.

Threads made by Claude Sonnet 5.5 (before 2026-10-07's switch) are still shown,
read-only: their stored content is Anthropic message blocks.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

import openai
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

PROMPT_VERSION = "v2"
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
MAX_TOOL_ROUNDS = 3

FIRST_TURN = (
    "Analyse this match. Work out your probabilities, compare them with the prices across all the markets, "
    "record your analysis with record_analysis, then give Ivo and Sam a short summary."
)

_PROB = {"type": "number", "description": "0 to 1"}
RECORD_ANALYSIS = {
    "type": "function",
    "name": "record_analysis",
    "description": (
        "Record your structured analysis of this match: your probabilities, the bets you suggest (if any) and "
        "why. Call it once per full analysis, and again whenever your view changes; the latest call before "
        "kick-off is the one your track record is judged on."
    ),
    "strict": True,
    "parameters": {
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
    """Rough first-turn cost: two calls (tool round trip), the second mostly cached."""
    inp, out, cached = config.AI_PRICES.get(config.AI_MODEL, config.AI_PRICES[config.DEFAULT_AI_MODEL])
    tokens_in = len(bundle_text) / 3.2 + len(SYSTEM_PROMPT) / 4 + 1500
    return round((tokens_in * inp + tokens_in * cached + 6000 * out) / 1_000_000, 4)


def _user_item(*texts: str) -> dict:
    return {"role": "user", "content": [{"type": "input_text", "text": t} for t in texts]}


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
        _user_item(f"<match_bundle>\n{text}\n</match_bundle>", FIRST_TURN),
    ])))
    db.commit()
    return thread


def add_user_message(db: Session, thread: AiThread, user: User, text: str) -> None:
    db.add(AiMessage(thread_id=thread.id, role="user", author=user.display_name,
                     content_json=json.dumps([_user_item(text)])))
    db.commit()


def is_legacy(thread: AiThread) -> bool:
    """Claude-era threads store Anthropic blocks and can't be continued."""
    return thread.model.startswith("claude")


def _history(db: Session, thread: AiThread) -> list[dict]:
    """The conversation as Responses API input items, exactly as stored (append-only)."""
    items = []
    for m in db.scalars(select(AiMessage).where(AiMessage.thread_id == thread.id).order_by(AiMessage.id)):
        items += json.loads(m.content_json)
    return items


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
    """Send the thread to the model and handle function calls until it finishes its reply."""
    client = make_client()
    fx = db.get(Fixture, thread.fixture_id)
    recorded, cost = [], 0.0
    for _ in range(MAX_TOOL_ROUNDS):
        try:
            resp = client.responses.create(
                model=thread.model,
                instructions=SYSTEM_PROMPT,
                input=_history(db, thread),
                tools=[RECORD_ANALYSIS],
                reasoning={"effort": thread.effort},
                max_output_tokens=32000,
                store=False,
                include=["reasoning.encrypted_content"],
            )
        except openai.RateLimitError as e:
            raise AiError("The model is rate-limited right now; try again in a minute") from e
        except openai.APIStatusError as e:
            raise AiError(f"Model API error {e.status_code}: {e.message}") from e
        except openai.APIConnectionError as e:
            raise AiError(f"Couldn't reach the model: {e}") from e

        u = resp.usage
        c = cost_usd(thread.model, u)
        cost += c
        output = [o.model_dump(mode="json", exclude_none=True) for o in resp.output]
        calls = [o for o in output if o.get("type") == "function_call"]
        refusal = next((p.get("refusal") for o in output if o.get("type") == "message"
                        for p in o.get("content", []) if p.get("type") == "refusal"), None)
        details = getattr(u, "input_tokens_details", None)
        cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
        db.add(AiMessage(
            thread_id=thread.id, role="assistant",
            stop_reason="refusal" if refusal else "tool_use" if calls else resp.status,
            content_json=json.dumps(output),
            input_tokens=(u.input_tokens or 0) - cached, output_tokens=u.output_tokens or 0,
            cache_read_tokens=cached, cost_usd=c,
        ))
        db.commit()

        if refusal:
            raise AiError(f"The model declined to answer: {refusal}")
        if resp.status == "incomplete":
            reason = getattr(resp.incomplete_details, "reason", None) if resp.incomplete_details else None
            raise AiError(f"The model's reply was cut short ({reason or 'incomplete'})")
        if not calls:
            break

        results = []
        for call in calls:
            if call["name"] == "record_analysis":
                try:
                    args = json.loads(call["arguments"])
                except ValueError:
                    pred, text = None, "Not recorded: the arguments weren't valid JSON. Please call it again."
                else:
                    pred, text = _record(db, thread, fx, user_id, args, call["call_id"])
                if pred:
                    recorded.append(pred.id)
            else:
                text = f"Unknown function {call['name']}"
            results.append({"type": "function_call_output", "call_id": call["call_id"], "output": text})
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


def _texts_and_calls(blocks: list[dict]) -> tuple[list[str], list[str]]:
    """Visible text and record_analysis call ids from stored content, in either
    format: Responses API items (Luna) or Anthropic blocks (Claude-era threads)."""
    texts, calls = [], []
    for b in blocks:
        t = b.get("type")
        if t == "message" or (t is None and "content" in b):  # Responses message / input item
            for part in b.get("content", []):
                if part.get("type") in ("output_text", "input_text") and part.get("text"):
                    texts.append(part["text"])
        elif t == "text" and b.get("text"):  # Anthropic
            texts.append(b["text"])
        elif t == "function_call" and b.get("name") == "record_analysis":
            calls.append(b.get("call_id"))
        elif t == "tool_use" and b.get("name") == "record_analysis":
            calls.append(b.get("id"))
    return texts, calls


def thread_view(db: Session, thread: AiThread) -> dict:
    """The thread as the UI shows it: typed messages, the model's text, analyses."""
    preds = {p.id: p for p in db.scalars(select(AiPrediction).where(AiPrediction.thread_id == thread.id))}
    tips = list(db.scalars(select(Tip).where(Tip.ai_prediction_id.in_(preds.keys())))) if preds else []
    by_tool_use = {p.tool_use_id: p.id for p in preds.values()}
    msgs, spent = [], 0.0
    for m in db.scalars(select(AiMessage).where(AiMessage.thread_id == thread.id).order_by(AiMessage.id)):
        spent += m.cost_usd or 0
        texts, calls = _texts_and_calls(json.loads(m.content_json))
        if m.role == "user":
            typed = [t for t in texts if not t.startswith("<match_bundle>") and t != FIRST_TURN]
            if typed:
                msgs.append({"id": m.id, "role": "user", "author": m.author, "text": "\n".join(typed),
                             "created_at": m.created_at})
            continue
        text = "\n\n".join(texts)
        entry = {"id": m.id, "role": "assistant", "text": text, "created_at": m.created_at,
                 "stop_reason": m.stop_reason}
        ids = [by_tool_use[c] for c in calls if c in by_tool_use]
        if ids:
            entry["prediction_id"] = ids[-1]
        if text or calls:
            msgs.append(entry)
    return {
        "id": thread.id, "fixture_id": thread.fixture_id, "model": thread.model, "effort": thread.effort,
        "prompt_version": thread.prompt_version, "created_by": thread.created_by, "created_at": thread.created_at,
        "bundle_built_at": json.loads(thread.bundle_json).get("bundle_built_at"),
        "cost_usd": round(spent, 4),
        "read_only": is_legacy(thread),
        "messages": msgs,
        "predictions": [
            {"id": p.id, "created_at": p.created_at, "model": p.model, "analysis": json.loads(p.analysis_json),
             "market_probs": json.loads(p.market_probs_json) if p.market_probs_json else None,
             "tips": [t.id for t in tips if t.ai_prediction_id == p.id]}
            for p in preds.values()
        ],
    }
