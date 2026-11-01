"""Staking plan: bundling picks, exact stakes after a loss, settling from the legs, and the run resetting on a win."""
from .conftest import KICKOFF, af_fixture

API = "/api/v1"


def test_staking_plan(client, auth, fake):
    fake.af_fixtures = [af_fixture(1001, (50, "Manchester City"), (39, "Wolves"), KICKOFF),
                        af_fixture(1002, (40, "Liverpool"), (42, "Arsenal"), KICKOFF)]
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39], "include_standings": False}, headers=auth)
    assert client.get(f"{API}/staking").status_code == 401

    def pick(fixture_id, market, selection, odds, line=None):
        r = client.post(f"{API}/admin/tips", headers=auth, json={
            "fixture_id": fixture_id, "market": market, "selection": selection, "line": line, "odds": odds})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def settle(tip_id, status):
        assert client.post(f"{API}/admin/tips/{tip_id}/settle", headers=auth, json={"status": status}).status_code == 200

    def bundle(*tip_ids):
        return client.post(f"{API}/staking/bundles", headers=auth, json={"tip_ids": list(tip_ids)})

    city, away, over = pick(1001, "1X2", "home", 2.0), pick(1002, "1X2", "away", 3.0), pick(1001, "OU", "over", 1.5, 1.5)
    s = client.get(f"{API}/staking", headers=auth).json()
    assert s["current"] is None and s["run"] == {"number": 1, "step": 1, "losses": 0.0, "next_stake": 6.0}
    assert s["plan"]["target_profit"] == 30.0 and s["plan"]["multiplier"] == 1.2 and s["plan"]["survivable_losses"] == 9

    assert bundle(city, over).status_code == 409  # same match twice
    b = bundle(city, away).json()
    assert b["odds"] == 6.0 and b["stake"] == 6.0 and (b["run"], b["step"]) == (1, 1)
    assert bundle(over).status_code == 409  # one bundle at a time
    assert client.delete(f"{API}/admin/tips/{city}", headers=auth).status_code == 409

    # One leg lost settles the bundle; the next stake covers the £6 lost plus the £30 target at whatever odds.
    settle(city, "lost")
    s = client.get(f"{API}/staking", headers=auth).json()
    assert s["current"] is None and s["history"][0]["status"] == "lost" and s["history"][0]["profit"] == -6.0
    assert s["run"] == {"number": 1, "step": 2, "losses": 6.0, "next_stake": 7.2}

    goals = pick(1002, "OU", "over", 2.5, 2.5)
    b = bundle(over, goals).json()
    assert b["odds"] == 3.75 and b["stake"] == round(36 / 2.75, 2) and b["step"] == 2

    # A void leg counts at 1.00; putting it back to pending reopens the bundle until it's decided again.
    settle(over, "won")
    settle(goals, "void")
    assert client.get(f"{API}/staking", headers=auth).json()["history"][0]["profit"] == round(13.09 * 0.5, 2)
    settle(goals, "pending")
    assert client.get(f"{API}/staking", headers=auth).json()["current"]["id"] == b["id"]
    settle(goals, "won")
    s = client.get(f"{API}/staking", headers=auth).json()
    assert s["run"] == {"number": 2, "step": 1, "losses": 0.0, "next_stake": 6.0}
    assert s["stats"] == {"bundles": 2, "won": 1, "lost": 1, "runs_completed": 1, "profit": 30.0, "bank_now": 180.0,
                          "longest_losing_streak": 1}

    r = client.put(f"{API}/staking/plan", headers=auth, json={"base_stake": 3, "target_odds": 6, "bank": 150})
    assert r.json()["run"]["next_stake"] == 3.0 and r.json()["plan"]["survivable_losses"] == 13
