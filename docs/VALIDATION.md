# Validation in the build environment

- Python 3.12 with the pinned requirements: pytest returned **5 passed, 1 skipped**.
- Passed: credential validation, duplicate accounts, JWT protection, matchmaking demo flow, unauthorized result rejection, session winner validation, duplicate result rejection, leaderboard order/cache parity, queue cancellation, Redis failure fallback, health and metrics.
- Skipped: PostgreSQL concurrency test because this environment has no PostgreSQL service.
- Docker, PostgreSQL, and Redis server binaries are not available in this environment. Container startup and real-service CI have not been executed here.
- GitHub Actions is configured to run the real-service concurrency test when this repository is pushed to GitHub.
- No load test or AWS deployment has been run. There are no measured throughput or latency claims.
