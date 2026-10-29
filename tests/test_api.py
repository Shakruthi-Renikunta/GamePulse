import os
from concurrent.futures import ThreadPoolExecutor
import pytest
import redis
from app import main


def test_auth_and_validation(client):
    body = {"username": "Alice", "password": "Password123!"}
    response = client.post("/auth/register", json=body)
    assert response.status_code == 201
    assert "password_hash" not in response.json()
    assert client.post("/auth/register", json=body).status_code == 409
    assert client.post("/auth/register", json={"username": "x", "password": "short"}).status_code == 422
    assert client.post("/auth/login", json={**body, "password": "wrongpass"}).status_code == 401
    assert client.get("/players/me", headers={"Authorization": "Bearer broken"}).status_code == 401
    assert client.get("/players/me").status_code in (401, 403)


def test_match_result_and_cache(client, players):
    (a, ah), (b, bh), (c, ch) = players
    assert client.get("/players/me", headers=ah).json()["id"] == a["id"]
    assert client.post("/matchmaking/join", headers=ah).json() == {"status": "queued"}
    assert client.post("/matchmaking/join", headers=ah).json() == {"status": "queued"}
    match = client.post("/matchmaking/join", headers=bh).json()
    sid = match["session_id"]
    assert client.post("/matchmaking/join", headers=ah).json()["session_id"] == sid
    assert client.get("/sessions/me", headers=ch).json() == []
    assert len(client.get("/sessions/me", headers=ah).json()) == 1
    payload = {"winner_id": a["id"], "points": 150}
    url = f"/sessions/{sid}/result"
    assert client.post(url, json=payload, headers=ah).status_code == 403
    server = {"X-Game-Server-Key": main.SERVER_KEY}
    assert client.post(url, json={**payload, "winner_id": c["id"]}, headers=server).status_code == 422
    assert client.post(url, json=payload, headers=server).json()["winner"]["score"] == 150
    assert client.post(url, json=payload, headers=server).status_code == 409
    first = client.get("/leaderboard")
    second = client.get("/leaderboard")
    assert first.json() == second.json()
    assert first.json()[0]["id"] == a["id"]
    assert second.headers["X-Cache"] == "HIT"
    assert client.get("/players/me", headers=ah).json()["score"] == 150
    assert client.get("/leaderboard?limit=101").status_code == 422


def test_ties_and_cancel(client, players):
    a, ah = players[0]
    assert client.get("/leaderboard").json() == client.get("/leaderboard").json()
    client.post("/matchmaking/join", headers=ah)
    assert client.delete("/matchmaking/queue", headers=ah).status_code == 204
    assert client.post("/matchmaking/join", headers=players[1][1]).json()["status"] == "queued"


def test_cache_outage_fallback(client, players, monkeypatch):
    def fail(*args, **kwargs):
        raise redis.ConnectionError("test outage")
    monkeypatch.setattr(main.cache, "zrevrange", fail)
    monkeypatch.setattr(main.cache, "pipeline", fail)
    assert len(client.get("/leaderboard").json()) == 3
    monkeypatch.setattr(main.cache, "ping", fail)
    assert client.get("/health/ready").status_code == 503
    assert client.get("/health/live").status_code == 200


def test_metrics(client):
    client.get("/health/live")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "gamepulse_request_seconds_bucket" in response.text


@pytest.mark.skipif(os.environ.get("REAL_SERVICES") != "1", reason="Requires PostgreSQL advisory locks")
def test_concurrent_joins_and_results(client, players):
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda p: client.post("/matchmaking/join", headers=p[1]), players))
    assert all(r.status_code == 200 for r in responses)
    sessions = [client.get("/sessions/me", headers=p[1]).json() for p in players]
    unique = {g["id"] for games in sessions for g in games}
    assert len(unique) == 1
    game = next(g for games in sessions for g in games)
    url = f"/sessions/{game['id']}/result"
    def submit(_):
        return client.post(url, json={"winner_id": game["players"][0]}, headers={"X-Game-Server-Key": main.SERVER_KEY})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
