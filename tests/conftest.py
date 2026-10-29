import os
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters")
os.environ.setdefault("GAME_SERVER_KEY", "test-server-key-at-least-32-characters")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import main
from app.db import Base, get_db, engine as production_engine

@pytest.fixture
def client():
    real = os.environ.get("REAL_SERVICES") == "1"
    engine = production_engine if real else create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    def override():
        with factory() as db:
            yield db
    main.app.dependency_overrides[get_db] = override
    original = main.cache
    if not real:
        main.cache = fakeredis.FakeRedis(decode_responses=True)
    main.cache.flushdb()  # CI uses isolated Redis database 15; never run on production.
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
    main.cache = original
    Base.metadata.drop_all(engine)
    if not real:
        engine.dispose()

@pytest.fixture
def players(client):
    result = []
    for username in ["alice", "bob", "carol"]:
        body = {"username": username, "password": "Password123!"}
        player = client.post("/auth/register", json=body).json()
        token = client.post("/auth/login", json=body).json()["access_token"]
        result.append((player, {"Authorization": f"Bearer {token}"}))
    return result
