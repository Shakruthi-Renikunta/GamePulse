import hmac
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import redis
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy import select, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import Base, engine, get_db, Player, Game, QueueEntry

SECRET = os.environ.get("JWT_SECRET", "")
SERVER_KEY = os.environ.get("GAME_SERVER_KEY", "")
if len(SECRET) < 32 or len(SERVER_KEY) < 32:
    raise RuntimeError("Set JWT_SECRET and GAME_SERVER_KEY to separate random values of at least 32 characters")
cache = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
passwords = PasswordHash.recommended()
bearer = HTTPBearer()
requests = Counter("gamepulse_requests_total", "HTTP requests", ["method", "route", "status"])
latency = Histogram("gamepulse_request_seconds", "Request latency", ["method", "route"])
log = logging.getLogger("gamepulse")

@asynccontextmanager
async def lifespan(app):
    # One init process is used in Compose; avoid schema changes in request handlers.
    yield

app = FastAPI(title="GamePulse", version="0.1.0", lifespan=lifespan)

@app.middleware("http")
async def observe(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = getattr(request.scope.get("route"), "path", "unmatched")
    if route != "/metrics":
        requests.labels(request.method, route, str(response.status_code)).inc()
        latency.labels(request.method, route).observe(time.perf_counter() - start)
    return response

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)

class Result(BaseModel):
    winner_id: str
    points: int = Field(default=100, ge=0, le=1000)


def current_player(auth: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(auth.credentials, SECRET, algorithms=["HS256"], options={"require": ["sub", "exp"]})
        player = db.get(Player, payload["sub"])
        if player is None:
            raise ValueError()
        return player
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(401, "Invalid or expired token")


def public(player):
    return {"id": player.id, "username": player.username, "score": player.score}


def matchmaking_lock(db):
    # All queue and game lifecycle mutations acquire the same transaction lock.
    # PostgreSQL lock works across API replicas. SQLite is for sequential tests only.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(438219)"))

@app.post("/auth/register", status_code=201)
def register(body: Credentials, db: Session = Depends(get_db)):
    player = Player(id=str(uuid4()), username=body.username.lower(), password_hash=passwords.hash(body.password))
    db.add(player)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Username already exists")
    return public(player)

@app.post("/auth/login")
def login(body: Credentials, db: Session = Depends(get_db)):
    player = db.scalar(select(Player).where(Player.username == body.username.lower()))
    if player is None or not passwords.verify(body.password, player.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = jwt.encode({"sub": player.id, "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, SECRET, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer"}

@app.get("/players/me")
def me(player: Player = Depends(current_player)):
    return public(player)

@app.get("/leaderboard")
def leaderboard(response: Response, limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    # Each cached snapshot is populated atomically with MULTI/EXEC and expires.
    # DB is authoritative; cache is allowed to lag at most five seconds.
    key = f"gamepulse:leaderboard:{limit}"
    try:
        rows = cache.zrevrange(key, 0, limit - 1, withscores=True)
        if rows:
            response.headers["X-Cache"] = "HIT"
            return [{**json.loads(member), "score": int(score), "rank": i + 1} for i, (member, score) in enumerate(rows)]
    except redis.RedisError:
        log.warning("Redis unavailable; reading leaderboard from database")
    players = db.scalars(select(Player).order_by(Player.score.desc(), Player.id.desc()).limit(limit)).all()
    result = [{**public(p), "rank": i + 1} for i, p in enumerate(players)]
    try:
        if players:
            # Member begins with ID to preserve the same deterministic tie ordering as SQL.
            members = {json.dumps({"id": p.id, "username": p.username}, separators=(",", ":")): p.score for p in players}
            with cache.pipeline() as pipe:
                pipe.delete(key)
                pipe.zadd(key, members)
                pipe.expire(key, 5)
                pipe.execute()
    except redis.RedisError:
        pass
    response.headers["X-Cache"] = "MISS"
    return result

@app.post("/matchmaking/join")
def join(player: Player = Depends(current_player), db: Session = Depends(get_db)):
    matchmaking_lock(db)
    active = db.scalar(select(Game).where(Game.status == "active", or_(Game.player_one == player.id, Game.player_two == player.id)))
    if active:
        return {"status": "matched", "session_id": active.id}
    opponent = db.scalar(select(QueueEntry).where(QueueEntry.player_id != player.id).order_by(QueueEntry.joined_at, QueueEntry.player_id).limit(1))
    if opponent is None:
        if db.get(QueueEntry, player.id) is None:
            db.add(QueueEntry(player_id=player.id, joined_at=int(time.time())))
        db.commit()
        return {"status": "queued"}
    own = db.get(QueueEntry, player.id)
    if own:
        db.delete(own)
    game = Game(id=str(uuid4()), player_one=opponent.player_id, player_two=player.id)
    db.delete(opponent)
    db.add(game)
    db.commit()
    return {"status": "matched", "session_id": game.id}

@app.delete("/matchmaking/queue", status_code=204)
def leave(player: Player = Depends(current_player), db: Session = Depends(get_db)):
    matchmaking_lock(db)
    entry = db.get(QueueEntry, player.id)
    if entry:
        db.delete(entry)
    db.commit()
    return Response(status_code=204)

@app.get("/sessions/me")
def sessions(player: Player = Depends(current_player), db: Session = Depends(get_db)):
    games = db.scalars(select(Game).where(or_(Game.player_one == player.id, Game.player_two == player.id)).order_by(Game.id).limit(100)).all()
    return [{"id": g.id, "players": [g.player_one, g.player_two], "status": g.status, "winner_id": g.winner_id} for g in games]

@app.post("/sessions/{session_id}/result")
def finish(session_id: str, body: Result, x_game_server_key: str = Header(default=""), db: Session = Depends(get_db)):
    if not hmac.compare_digest(x_game_server_key, SERVER_KEY):
        raise HTTPException(403, "Game server credentials required")
    matchmaking_lock(db)
    game = db.get(Game, session_id)
    if not game:
        raise HTTPException(404, "Session not found")
    if game.status != "active":
        raise HTTPException(409, "Result already recorded")
    if body.winner_id not in (game.player_one, game.player_two):
        raise HTTPException(422, "Winner must belong to this session")
    winner = db.get(Player, body.winner_id)
    winner.score += body.points
    game.status, game.winner_id = "completed", winner.id
    db.commit()
    return {"session_id": game.id, "status": game.status, "winner": public(winner)}

@app.get("/health/live")
def live():
    return {"status": "ok"}

@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        cache.ping()
    except Exception:
        raise HTTPException(503, "Dependency unavailable")
    return {"status": "ready"}

@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
