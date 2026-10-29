# Seven days, eight hours each day

| Day | First 2 hours | Next 4 hours | Final 2 hours |
|---|---|---|---|
| 1 | HTTP, JSON, request/response, status codes | Run Docker stack; follow every Swagger demo step | Explain each endpoint aloud and draw the architecture |
| 2 | Python functions, classes, imports, type hints | Read registration/login; change a validation rule and verify it | Explain hashing, JWT, authentication vs authorization |
| 3 | SQL tables, keys, transactions | Trace players, sessions, scores; inspect PostgreSQL data | Explain duplicate result prevention and transaction rollback |
| 4 | Redis sorted sets and cache TTL | Trace leaderboard cache; test database fallback | Explain stale data, cache hit/miss, source of truth |
| 5 | Docker images, containers, volumes, networks | Rebuild stack; read CI; push to your own GitHub repository | Review test failures and practice Git commands |
| 6 | Latency, throughput, percentiles, concurrency | Run Locust; inspect Prometheus; save actual measurements | Explain the global lock bottleneck and scaling options |
| 7 | AWS architecture and reliability basics | Fix remaining issues; improve README with screenshots/results | Rehearse a five-minute demo and project interview questions |

This allocates all 56 hours to GamePulse. If dividing time with another project, reserve four hours per day for each and reduce AWS work to explaining the deployment design.

## Explain it simply

A player sends an HTTP request to FastAPI. FastAPI validates the data, checks their token, and reads or writes PostgreSQL. For leaderboard requests it first checks a temporary Redis copy. Docker gives every service a repeatable runtime. GitHub Actions runs tests whenever code changes. Prometheus collects request counts and time distributions.

## Questions to prepare

1. Why is PostgreSQL the source of truth even though Redis holds leaderboard data?
2. What happens if two players join at exactly the same time?
3. How do you prevent a client from awarding itself points?
4. What happens if the game server retries a completed result?
5. What still works when Redis goes down? What fails when PostgreSQL goes down?
6. Why can a global lock limit scalability? How would game-mode partitioning help?
7. What do p95 and requests per second measure?
8. What does CI verify, and what additional steps make continuous deployment?
9. Why is a Docker volume needed for PostgreSQL?
10. Which improvements would you prioritize before exposing this publicly?

Answer with code paths and actual measurements. Describe this as a backend MVP with a scaling design until you have measured its limits.

## Official learning references

- FastAPI: https://fastapi.tiangolo.com/tutorial/
- Password hashing and JWT: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- Redis sorted sets: https://redis.io/docs/latest/develop/data-types/sorted-sets/
- Docker Compose: https://docs.docker.com/compose/
- GitHub Actions: https://docs.github.com/en/actions
