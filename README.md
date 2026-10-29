# GamePulse

An interview project for multiplayer gameplay services: account authentication, FIFO two-player matchmaking, sessions, server-authorized score submission, a Redis-backed leaderboard, tests, Docker, CI, and Prometheus metrics.

This is a runnable MVP, not a real-time game simulation. No AWS resources have been deployed, no latency numbers are claimed, and automated deployment is not yet configured. CI runs tests against PostgreSQL/Redis and builds the image.

## Start on Windows with Docker Desktop

1. Install Python 3.12, Git, and Docker Desktop with Linux containers. Open Docker Desktop.
2. Extract this folder. Open it in VS Code (File → Open Folder → gamepulse).
3. Open the VS Code PowerShell terminal in the folder containing `compose.yaml`.
4. Copy the configuration:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32)); print(secrets.token_hex(32)); print(secrets.token_hex(24))"
```

Edit `.env`. Use the first random value for JWT_SECRET, the second for GAME_SERVER_KEY, and the third for POSTGRES_PASSWORD. Hex characters avoid connection URL escaping issues. Never commit `.env`.

```powershell
docker compose up --build -d
docker compose ps
docker compose logs api
```

Open http://localhost:8000/docs for the interactive API and http://localhost:9090 for Prometheus. First launch downloads images and dependencies. Use `docker compose down` to stop; the database volume persists.

## Demonstrate the entire flow in Swagger

1. POST `/auth/register` with `{"username":"alice","password":"Password123!"}`. Copy the returned ID.
2. Register `bob` with the same example password. Copy Bob's ID.
3. POST `/auth/login` as Alice. Copy `access_token`.
4. Click **Authorize**, paste only the token, and authorize.
5. GET `/players/me`; then POST `/matchmaking/join`. Alice is queued.
6. Login as Bob, replace the token using Authorize, and join matchmaking. A session ID is returned.
7. GET `/sessions/me`. Bob and Alice now share one active session.
8. POST `/sessions/{session_id}/result` with Alice's ID as `winner_id` and `points:150`. Supply GAME_SERVER_KEY from `.env` in the `x-game-server-key` input. This simulates the trusted game server. Never embed this secret in a player client.
9. GET `/leaderboard` twice: Alice is first; response header `X-Cache` changes from MISS to HIT. After five seconds a new snapshot is built.
10. Submit the result again: HTTP 409 proves a session cannot award points twice.

The first queued player can discover their match by polling `/sessions/me` or joining again. GET session history currently returns up to 100 records ordered by ID, not by creation time.

## Learn the files

| File | Purpose |
|---|---|
| app/db.py | PostgreSQL tables and one database session per request |
| app/main.py | API routes, authentication, cache, matchmaking, metrics |
| app/init_db.py | Explicit initial schema creation |
| compose.yaml | Starts database, Redis, API, and Prometheus |
| tests/ | Authentication, results, cache failure, concurrency tests |
| .github/workflows/ci.yml | Test with real services and build Docker image |
| locustfile.py | Read traffic workload |
| docs/LEARNING_PLAN.md | Seven-day build and interview plan |
| docs/AWS.md | Deployment design and remaining work |

## Tests

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Local tests use temporary SQLite and fake Redis, and skip the PostgreSQL concurrency test. GitHub Actions runs that test with real PostgreSQL/Redis. Tests drop/recreate the configured tables and flush the configured Redis database when REAL_SERVICES=1: use dedicated test services only.

## Load test and latency

With Docker running, activate the Python environment and run:

```powershell
locust -f locustfile.py --host http://localhost:8000 --headless -u 20 -r 5 -t 60s --csv gamepulse-load
```

Seed players first. This workload measures leaderboard reads plus health requests. Record CPU/RAM, concurrency, request count, errors, throughput, and p50/p95/p99. Compare a warm cache with cache outage using disposable local infrastructure; it is not a complete matchmaking stress test. Do not claim scalability from this read-only workload.

Prometheus queries:

```promql
rate(gamepulse_requests_total[1m])
histogram_quantile(0.95, sum by (le, route) (rate(gamepulse_request_seconds_bucket[5m])))
```

Metrics are designed for one process per container; multiple containers need their own scrape targets and aggregated queries.

## Design choices and limits

- PostgreSQL is authoritative for scores, queue entries, and sessions. Completing a session and incrementing the winner's score happen in one transaction.
- A PostgreSQL transaction advisory lock serializes matchmaking, cancellation, and results across API instances. This prevents duplicate active sessions but becomes a throughput bottleneck; partition by game mode/region when measured traffic requires it.
- Redis sorted-set snapshots cache the top N players for five seconds. Redis loss falls back to SQL. Ties use descending player UUID, consistently in SQL and Redis. Snapshot freshness also depends on request/database execution time; slow in-flight readers can briefly repopulate older snapshots.
- Queue has FIFO second-level timestamps, UUID tie-breaks, and explicit cancellation. No heartbeat/expiry, region, skill matching, or disconnect cleanup yet.
- Passwords use Argon2; JWTs expire after one hour. No refresh/revoke, email verification, login throttling, or rate limits yet. Run privately until those controls and HTTPS are added.
- Schema initialization uses create_all for a fresh database. Add Alembic migrations before evolving a deployed schema.
- Indexes, pagination, game-server key rotation, audit logs, backups, cache stampede control, and production load testing are follow-up work.

## Troubleshooting

- Docker connection error: start Docker Desktop and use Linux containers.
- Port 8000 busy: change the left side of `127.0.0.1:8000:8000` to `8001` and open localhost:8001.
- HTTP 401: login again and replace the Bearer token.
- HTTP 403 submitting results: use the server key, not a JWT.
- Redis outage: leaderboard stays available through SQL; readiness returns 503.
- Database password changed after first launch: the stored database still has the old password. Restore the old value or deliberately recreate disposable development data. `docker compose down -v` permanently deletes that development database.
