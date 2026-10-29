import os
from sqlalchemy import create_engine, String, Integer, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

URL = os.environ.get("DATABASE_URL", "sqlite:///./gamepulse.db")
engine = create_engine(URL, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Player(Base):
    __tablename__ = "players"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    score: Mapped[int] = mapped_column(Integer, default=0)

class Game(Base):
    __tablename__ = "games"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    player_one: Mapped[str] = mapped_column(ForeignKey("players.id"))
    player_two: Mapped[str] = mapped_column(ForeignKey("players.id"))
    status: Mapped[str] = mapped_column(String(16), default="active")
    winner_id: Mapped[str | None] = mapped_column(ForeignKey("players.id"), nullable=True)

class QueueEntry(Base):
    __tablename__ = "queue_entries"
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), primary_key=True)
    joined_at: Mapped[int] = mapped_column(Integer)

def get_db():
    with SessionLocal() as db:
        yield db
