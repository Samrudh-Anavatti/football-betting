"""AI analysis with a fake Claude: tool call -> prediction + private AI tips -> chat."""
from anthropic.types import Message

from app import config
from app.ai import client as ai_client
from app.ai import service

API = "/api/v1"


def _msg(content, stop_reason, n=1):
    return Message.model_validate({
        "id": f"msg_{n}", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 200, "cache_creation_input_tokens": 1000,
                  "cache_read_input_tokens": 0},
    })


ANALYSIS = {
    "summary": "City should win but the price is fair; Wolves concede plenty.",
    "probabilities": {"home_win": 0.7, "draw": 0.18, "away_win": 0.12, "over_2_5_goals": 0.62, "both_teams_score": 0.5},
    "suggested_bets": [
        {"market_id": 5, "market": "Goals Over/Under", "value": "Over 2.5", "your_probability": 0.66,
         "min_odds": 1.55, "stake_units": 1.5, "confidence": 3, "reasoning": "Both leaky."},
        {"market_id": 12, "market": "Double Chance", "value": "Home/Draw", "your_probability": 0.95,
         "min_odds": 1.5, "stake_units": 1, "confidence": 2, "reasoning": "Too short now."},
    ],
    "key_factors": ["Wolves' away defence"],
    "data_gaps": ["No line-ups"],
    "no_bet": False,
}


class FakeClaude:
    def __init__(self):
        self.requests = []
        self.messages = self

    def create(self, **kw):
        self.requests.append(kw)
        last = kw["messages"][-1]["content"]
        if any(b.get("type") == "tool_result" for b in last):
            return _msg([{"type": "text", "text": "Over 2.5 is the bet."}], "end_turn", len(self.requests))
        if "Analyse this match" in last[-1]["text"]:
            return _msg([
                {"type": "thinking", "thinking": "", "signature": "sig"},
                {"type": "tool_use", "id": "toolu_1", "name": "record_analysis", "input": ANALYSIS},
            ], "tool_use", len(self.requests))
        return _msg([{"type": "text", "text": "Still Over 2.5."}], "end_turn", len(self.requests))


def test_analysis_chat_and_record(client, auth, fake, monkeypatch):
    claude = FakeClaude()
    monkeypatch.setattr(service, "make_client", lambda: claude)
    monkeypatch.setattr(config, "FOUNDRY_RESOURCE", "res")
    monkeypatch.setattr(config, "FOUNDRY_API_KEY", "key")
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39]}, headers=auth)
    client.post(f"{API}/admin/sync/markets", json={"league_ids": [39]}, headers=auth)

    info = client.get(f"{API}/admin/matches/1001/ai", headers=auth).json()
    assert info["configured"] and info["estimate_usd"] > 0 and info["threads"] == []

    run = client.post(f"{API}/admin/matches/1001/ai", headers=auth).json()
    assert run["status"] == "ok" and run["items"] == 1, run
    first = claude.requests[0]
    assert first["model"] == "claude-sonnet-5-5" and first["tools"][0]["name"] == "record_analysis"
    assert "<match_bundle>" in first["messages"][0]["content"][0]["text"]
    # The tool result went back with the thinking block replayed unchanged.
    second = claude.requests[1]["messages"]
    assert second[1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig"}
    assert "1 bet tracked" in second[2]["content"][0]["content"]

    info = client.get(f"{API}/admin/matches/1001/ai", headers=auth).json()
    thread = info["threads"][0]
    assert thread["predictions"][0]["analysis"]["probabilities"]["home_win"] == 0.7
    assert thread["predictions"][0]["market_probs"]["result"]["home"] > 0.5
    assert [m["role"] for m in thread["messages"]] == ["assistant", "assistant"]
    assert thread["messages"][0]["prediction_id"] == thread["predictions"][0]["id"]
    # Over 2.5 tracked at the best price; Double Chance at 1.10 is below its 1.5 minimum.
    assert len(info["tips"]) == 1
    tip = info["tips"][0]
    assert tip["source"] == "ai" and not tip["published"] and tip["market"] == "OU" and tip["odds"] == 1.62

    # AI tips never appear publicly.
    assert client.get(f"{API}/tips").json() == []
    assert client.get(f"{API}/matches/1001").json()["tips"] == []

    run = client.post(f"{API}/admin/ai/threads/{thread['id']}/messages", headers=auth, json={"text": "Still?"}).json()
    assert run["status"] == "ok"
    assert len(claude.requests[-1]["messages"]) == 5  # append-only history
    msgs = client.get(f"{API}/admin/matches/1001/ai", headers=auth).json()["threads"][0]["messages"]
    assert msgs[-2] == {**msgs[-2], "role": "user", "text": "Still?", "author": "Ivo"}
    assert msgs[-1]["text"] == "Still Over 2.5."

    # Result: 3-1 -> the AI's over 2.5 wins and is scored against the market.
    from .conftest import KICKOFF, af_fixture
    fake.af_fixtures = [af_fixture(1001, (50, "Manchester City"), (39, "Wolves"), KICKOFF, "FT", 3, 1)]
    from datetime import timedelta
    from app.database import SessionLocal
    from app.models import AiPrediction, Fixture
    db = SessionLocal()
    db.get(Fixture, 1001).kickoff = db.get(AiPrediction, 1).created_at + timedelta(hours=1)
    db.commit()
    db.close()
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39], "include_standings": False}, headers=auth)
    s = client.get(f"{API}/admin/ai/summary", headers=auth).json()
    assert s["records"]["ai"]["won"] == 1 and s["records"]["ivo"]["tips"] == 0
    assert s["scores"]["matches"] == 1 and s["scores"]["result"]["ai"] is not None
    assert s["budget"]["spent_usd"] > 0


def test_budget_blocks_analysis(client, auth, fake, monkeypatch):
    monkeypatch.setattr(config, "FOUNDRY_RESOURCE", "res")
    monkeypatch.setattr(config, "FOUNDRY_API_KEY", "key")
    monkeypatch.setattr(config, "AI_MONTHLY_BUDGET_USD", 0.0)
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39]}, headers=auth)
    r = client.post(f"{API}/admin/matches/1001/ai", headers=auth)
    assert r.status_code == 402 and "budget" in r.json()["detail"]
    assert ai_client.configured()
