"""
SQLite-backed cache of Gemini contradiction verdicts.

Keyed by (old_memory_id, new_memory_id). Memories are immutable (there is
no update route), so a verdict for a given pair never goes stale.

Previously an in-memory dict -- verdicts vanished on restart, which meant
re-scoring after any restart re-spent the (rate-limited) Gemini quota on
pairs already resolved. Persisting removes that.

Time decay and access anomaly are still recomputed on every score request;
only the LLM verdict is cached.

detect_contradiction() never raises: on an API error or an unparseable
response it returns UNRELATED / 0.0 with a recognizable prefix in
`reasoning`. Those fallbacks must not be cached, otherwise one transient
failure (or a hit on the daily quota) would stick until restart.

If an update route is ever added, entries involving the edited memory
must be invalidated (delete rows where old_memory_id or new_memory_id
matches the edited id).
"""

from __future__ import annotations

from sqlalchemy import String, Float, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.core.contradiction import (
    ContradictionResult,
    MemoryRelationship,
    detect_contradiction,
)
from app.models.memory import Memory

# Must match the fallback messages in contradiction.detect_contradiction().
_FALLBACK_PREFIXES = ("API call failed", "Response did not parse to schema")


def _is_fallback(result: ContradictionResult) -> bool:
    return result.reasoning.startswith(_FALLBACK_PREFIXES)


class Base(DeclarativeBase):
    pass


class ContradictionVerdictRecord(Base):
    __tablename__ = "contradiction_verdicts"

    old_memory_id: Mapped[str] = mapped_column(String, primary_key=True)
    new_memory_id: Mapped[str] = mapped_column(String, primary_key=True)
    relationship: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(String, nullable=False)


class ContradictionCache:
    """
    Same call shape as before -- cache(old_memory, new_memory) -- so it
    still slots in anywhere a detector is expected.

    Defaults to an isolated in-memory SQLite database, so existing tests
    using `ContradictionCache()` with no arguments still get a fresh,
    empty cache per instance -- no test changes needed. Pass a real file
    URL for persistence across restarts.
    """

    def __init__(self, db_url: str = "sqlite:///:memory:") -> None:
        connect_args = (
            {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        )
        self._engine = create_engine(db_url, connect_args=connect_args)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)

    def __call__(self, old_memory: Memory, new_memory: Memory) -> ContradictionResult:
        with self._Session() as session:
            row = session.get(
                ContradictionVerdictRecord, (old_memory.id, new_memory.id)
            )
            if row is not None:
                return ContradictionResult(
                    relationship=MemoryRelationship(row.relationship),
                    score=row.score,
                    reasoning=row.reasoning,
                )

            result = detect_contradiction(old_memory=old_memory, new_memory=new_memory)
            if not _is_fallback(result):
                session.merge(
                    ContradictionVerdictRecord(
                        old_memory_id=old_memory.id,
                        new_memory_id=new_memory.id,
                        relationship=result.relationship.value,
                        score=result.score,
                        reasoning=result.reasoning,
                    )
                )
                session.commit()
            return result

    def __len__(self) -> int:
        with self._Session() as session:
            return session.query(ContradictionVerdictRecord).count()
