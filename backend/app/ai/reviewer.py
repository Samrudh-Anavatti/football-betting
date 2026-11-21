"""One structured question to a model, outside the match threads: Claude on Anthropic's API, or Luna on Foundry.

Both take a system prompt, one user message and a JSON schema, and give back the parsed answer with what the call
cost, so the caller can try Claude first and Luna when Claude can't (no key, month's budget spent, an error).
"""
import json
from dataclasses import dataclass

import anthropic
import openai

from .. import config
from . import client as luna


class ReviewError(Exception):
    pass


@dataclass
class Reply:
    data: dict
    provider: str  # claude | foundry
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


def configured(provider: str) -> bool:
    return bool(config.ANTHROPIC_API_KEY) if provider == "claude" else luna.configured()


def _parse(text: str, reply: "Reply") -> dict:
    try:
        return json.loads(text)
    except ValueError as e:
        raise SpentError("The model's answer wasn't valid JSON", reply) from e


def ask_claude(system: str, user: str, schema: dict) -> Reply:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=600, max_retries=2)
    try:
        resp = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            thinking={"type": "adaptive"},
            output_config={"effort": config.CLAUDE_EFFORT, "format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.RateLimitError as e:
        raise ReviewError("Claude is rate-limited right now") from e
    except anthropic.APIStatusError as e:
        raise ReviewError(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise ReviewError(f"Couldn't reach Claude: {e}") from e
    u = resp.usage
    inp, out, cache_read, cache_write = config.CLAUDE_PRICES.get(config.CLAUDE_MODEL, config.CLAUDE_PRICES["claude-opus-5-5"])
    read, written = u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0
    cost = round((u.input_tokens * inp + read * cache_read + written * cache_write + u.output_tokens * out) / 1_000_000, 6)
    reply = Reply({}, "claude", resp.model, u.input_tokens + read + written, u.output_tokens, cost)
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise SpentError(f"Claude stopped without an answer ({resp.stop_reason})", reply)
    reply.data = _parse(next((b.text for b in resp.content if b.type == "text"), ""), reply)
    return reply


def ask_luna(system: str, user: str, schema: dict) -> Reply:
    try:
        resp = luna.make_client().responses.create(
            model=config.AI_MODEL,
            instructions=system,
            input=[{"role": "user", "content": [{"type": "input_text", "text": user}]}],
            reasoning={"effort": config.AI_EFFORT},
            max_output_tokens=16000,
            store=False,
            text={"format": {"type": "json_schema", "name": "answer", "schema": schema, "strict": True}},
        )
    except openai.RateLimitError as e:
        raise ReviewError("Luna is rate-limited right now") from e
    except openai.APIStatusError as e:
        raise ReviewError(f"Luna API error {e.status_code}: {e.message}") from e
    except openai.APIConnectionError as e:
        raise ReviewError(f"Couldn't reach Luna: {e}") from e
    u = resp.usage
    reply = Reply({}, "foundry", config.AI_MODEL, u.input_tokens or 0, u.output_tokens or 0, luna.cost_usd(config.AI_MODEL, u))
    if resp.status != "completed":
        raise SpentError(f"Luna stopped without an answer ({resp.status})", reply)
    reply.data = _parse(resp.output_text, reply)
    return reply


class SpentError(ReviewError):
    """The call failed after it was billed: `reply` carries what it cost."""

    def __init__(self, message: str, reply: Reply):
        super().__init__(message)
        self.reply = reply


def ask(provider: str, system: str, user: str, schema: dict) -> Reply:
    return (ask_claude if provider == "claude" else ask_luna)(system, user, schema)
