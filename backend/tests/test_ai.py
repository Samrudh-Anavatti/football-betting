"""AI analysis with a fake model (Responses API shapes): function call ->
prediction + private AI tips -> chat -> settlement and scoring."""
import json
from types import SimpleNamespace as NS

from app import config
from app.ai import client as ai_client
from app.ai import service

API = "/api/v1"


class Item(dict):
    """Stands in for an SDK output item: model_dump() gives the dict back."""

    def model_dump(self, **_):
        return dict(self)


def _resp(output, n):
    usage = NS(input_tokens=30000, output_tokens=2000, input_tokens_details=NS(cached_tokens=20000 if n > 1 else 0))
    return NS(output=[Item(o) for o in output], usage=usage, status="completed", incomplete_details=None)


def _text(text):
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


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


class FakeModel:
    def __init__(self):
        self.requests = []
        self.responses = self

    def create(self, **kw):
        self.requests.append(kw)
        n = len(self.requests)
        last = kw["input"][-1]
        if last.get("type") == "function_call_output":
            return _resp([_text("Over 2.5 is the bet.")], n)
        if "Analyse this match" in last["content"][-1]["text"]:
            return _resp([
                {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "enc"},
                {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "record_analysis",
                 "arguments": json.dumps(ANALYSIS)},
            ], n)
        return _resp([_text("Still Over 2.5.")], n)


def _connect(monkeypatch):
    monkeypatch.setattr(config, "FOUNDRY_RESOURCE", "res")
    monkeypatch.setattr(config, "FOUNDRY_API_KEY", "key")


def test_analysis_chat_and_record(client, auth, fake, monkeypatch):
    model = FakeModel()
    monkeypatch.setattr(service, "make_client", lambda: model)
    _connect(monkeypatch)
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39]}, headers=auth)
    client.post(f"{API}/admin/sync/markets", json={"league_ids": [39]}, headers=auth)

    info = client.get(f"{API}/admin/matches/1001/ai", headers=auth).json()
    assert info["configured"] and info["estimate_usd"] > 0 and info["threads"] == []
    assert info["model"] == "gpt-5.6-luna"

    run = client.post(f"{API}/admin/matches/1001/ai", headers=auth).json()
    assert run["status"] == "ok" and run["items"] == 1, run
    first = model.requests[0]
    assert first["model"] == "gpt-5.6-luna" and first["tools"][0]["name"] == "record_analysis"
    assert first["tools"][0]["strict"] and first["store"] is False
    assert "<match_bundle>" in first["input"][0]["content"][0]["text"]
    # Second call replays the reasoning + function call unchanged, then the result.
    second = model.requests[1]["input"]
    assert second[1] == {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "enc"}
    assert second[3]["type"] == "function_call_output" and "1 bet tracked" in second[3]["output"]

    info = client.get(f"{API}/admin/matches/1001/ai", headers=auth).json()
    thread = info["threads"][0]
    assert thread["predictions"][0]["analysis"]["probabilities"]["home_win"] == 0.7
    assert thread["predictions"][0]["market_probs"]["result"]["home"] > 0.5
    assert [m["role"] for m in thread["messages"]] == ["assistant", "assistant"]
    assert thread["messages"][0]["prediction_id"] == thread["predictions"][0]["id"]
    assert thread["cost_usd"] > 0 and not thread["read_only"]
    # Over 2.5 tracked at the best price; Double Chance at 1.10 is below its 1.5 minimum.
    assert len(info["tips"]) == 1
    tip = info["tips"][0]
    assert tip["source"] == "ai" and not tip["published"] and tip["market"] == "OU" and tip["odds"] == 1.62

    # AI tips never appear publicly.
    assert client.get(f"{API}/tips").json() == []
    assert client.get(f"{API}/matches/1001").json()["tips"] == []

    run = client.post(f"{API}/admin/ai/threads/{thread['id']}/messages", headers=auth, json={"text": "Still?"}).json()
    assert run["status"] == "ok"
    assert len(model.requests[-1]["input"]) == 6  # append-only history
    msgs = client.get(f"{API}/admin/matches/1001/ai", headers=auth).json()["threads"][0]["messages"]
    assert msgs[-2] == {**msgs[-2], "role": "user", "text": "Still?", "author": "Ivo"}
    assert msgs[-1]["text"] == "Still Over 2.5."

    # Result: 3-1 -> the AI's over 2.5 wins and is scored against the market.
    from datetime import timedelta

    from app.database import SessionLocal
    from app.models import AiPrediction, Fixture

    from .conftest import KICKOFF, af_fixture
    fake.af_fixtures = [af_fixture(1001, (50, "Manchester City"), (39, "Wolves"), KICKOFF, "FT", 3, 1)]
    db = SessionLocal()
    db.get(Fixture, 1001).kickoff = db.get(AiPrediction, 1).created_at + timedelta(hours=1)
    db.commit()
    db.close()
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39], "include_standings": False}, headers=auth)
    s = client.get(f"{API}/admin/ai/summary", headers=auth).json()
    assert s["records"]["ai"]["won"] == 1 and s["records"]["ivo"]["tips"] == 0
    assert s["scores"]["matches"] == 1 and s["scores"]["result"]["ai"] is not None
    assert s["budget"]["spent_usd"] > 0


def test_claude_era_threads_are_read_only(client, auth, fake, monkeypatch):
    _connect(monkeypatch)
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39]}, headers=auth)
    from app.database import SessionLocal
    from app.models import AiMessage, AiThread
    db = SessionLocal()
    t = AiThread(fixture_id=1001, model="claude-sonnet-5-5", effort="high", prompt_version="v1",
                 bundle_json="{}", bundle_hash="x", created_by="Sam")
    db.add(t)
    db.flush()
    db.add(AiMessage(thread_id=t.id, role="assistant", content_json=json.dumps([{"type": "text", "text": "Old reply"}])))
    db.commit()
    tid = t.id
    db.close()
    thread = client.get(f"{API}/admin/matches/1001/ai", headers=auth).json()["threads"][0]
    assert thread["read_only"] and thread["messages"][0]["text"] == "Old reply"
    r = client.post(f"{API}/admin/ai/threads/{tid}/messages", headers=auth, json={"text": "hi"})
    assert r.status_code == 409


def test_budget_blocks_analysis(client, auth, fake, monkeypatch):
    _connect(monkeypatch)
    monkeypatch.setattr(config, "AI_MONTHLY_BUDGET_USD", 0.0)
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39]}, headers=auth)
    r = client.post(f"{API}/admin/matches/1001/ai", headers=auth)
    assert r.status_code == 402 and "budget" in r.json()["detail"]
    assert ai_client.configured()
