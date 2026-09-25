from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, Index, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.models.memory import Memory, MemoryCategory, StalenessScore


class Base(DeclarativeBase):
    pass


class LatestScoreRecord(Base):
    """Last computed StalenessScore per memory, so a page reload can show
    something better than "not checked" without recomputing (and without
    spending a Gemini call) for memories nobody has re-checked yet."""

    __tablename__ = "latest_scores"

    memory_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    score_json: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (Index("ix_latest_scores_scope", "user_id", "agent_id"),)


class MemoryRecord(Base):
    """SQLAlchemy table backing Memory. Mirrors app.models.memory.Memory
    field-for-field; conversion happens inside MemoryStore, so nothing
    above this module needs to know a database is involved."""

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    content: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_memories_scope", "user_id", "agent_id"),)


def _to_pydantic(row: MemoryRecord) -> Memory:
    return Memory(
        id=row.id,
        content=row.content,
        category=MemoryCategory(row.category),
        user_id=row.user_id,
        agent_id=row.agent_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_accessed_at=row.last_accessed_at,
        access_count=row.access_count,
    )


def _to_record(memory: Memory) -> MemoryRecord:
    return MemoryRecord(
        id=memory.id,
        content=memory.content,
        category=memory.category.value,
        user_id=memory.user_id,
        agent_id=memory.agent_id,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        last_accessed_at=memory.last_accessed_at,
        access_count=memory.access_count,
    )


class MemoryStore:
    """
    SQLite-backed repository for Memory objects (previously a plain
    in-memory dict -- see git history). Same public interface as before,
    so scorer/retrieval/API code needed zero changes.

    Defaults to an isolated in-memory SQLite database, so existing tests
    that do `MemoryStore()` with no arguments still get a fresh, empty
    store per instance -- no test changes needed. Pass a real file URL
    (e.g. "sqlite:///./contextclock.db") for persistence across restarts.
    """

    def __init__(self, db_url: str = "sqlite:///:memory:") -> None:
        connect_args = (
            {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        )
        self._engine = create_engine(db_url, connect_args=connect_args)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)

    def add(self, memory: Memory) -> Memory:
        with self._Session() as session:
            session.merge(_to_record(memory))
            session.commit()
        return memory

    def get(self, memory_id: str) -> Optional[Memory]:
        with self._Session() as session:
            row = session.get(MemoryRecord, memory_id)
            return _to_pydantic(row) if row is not None else None

    def list_for_scope(self, user_id: str, agent_id: str) -> list[Memory]:
        with self._Session() as session:
            rows = (
                session.query(MemoryRecord)
                .filter_by(user_id=user_id, agent_id=agent_id)
                .all()
            )
            return [_to_pydantic(r) for r in rows]

    def record_access(self, memory_id: str) -> Optional[Memory]:
        with self._Session() as session:
            row = session.get(MemoryRecord, memory_id)
            if row is None:
                return None
            row.access_count += 1
            row.last_accessed_at = datetime.utcnow()
            session.commit()
            return _to_pydantic(row)

    def save_latest_score(self, score: StalenessScore, user_id: str, agent_id: str) -> None:
        with self._Session() as session:
            session.merge(
                LatestScoreRecord(
                    memory_id=score.memory_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    score_json=score.model_dump_json(),
                )
            )
            session.commit()

    def get_scores_for_scope(self, user_id: str, agent_id: str) -> dict[str, StalenessScore]:
        with self._Session() as session:
            rows = session.query(LatestScoreRecord).filter_by(user_id=user_id, agent_id=agent_id).all()
            return {r.memory_id: StalenessScore.model_validate_json(r.score_json) for r in rows}
