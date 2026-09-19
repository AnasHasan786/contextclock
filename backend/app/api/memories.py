import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.memory import Memory, MemoryCategory, MemoryWithScore
from app.services.memory_store import MemoryStore
from app.core.scorer import score_memory_full

router = APIRouter(prefix="/memories", tags=["memories"])

# Single in-memory store shared by every request in this process.
# Swap for a database-backed store later without changing the routes.
_store = MemoryStore()


class MemoryCreate(BaseModel):
    """What a client sends to store a new memory. `id` is generated
    server-side so callers never have to worry about collisions."""

    content: str
    category: MemoryCategory
    user_id: str
    agent_id: str


@router.post("", response_model=Memory)
def create_memory(payload: MemoryCreate) -> Memory:
    memory = Memory(id=str(uuid.uuid4()), **payload.model_dump())
    return _store.add(memory)


@router.get("", response_model=list[Memory])
def list_memories(user_id: str, agent_id: str) -> list[Memory]:
    return _store.list_for_scope(user_id, agent_id)


@router.get("/{memory_id}/score", response_model=MemoryWithScore)
def get_memory_score(memory_id: str) -> MemoryWithScore:
    """Read-only: computing a staleness score is a diagnostic check,
    not genuine usage, so it must never bump access_count -- otherwise
    a monitoring/audit job that scores every memory would silently
    suppress the access-anomaly signal for everything it touches."""
    memory = _store.get(memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found.")

    existing = _store.list_for_scope(memory.user_id, memory.agent_id)
    score = score_memory_full(memory, existing_memories=existing)
    return MemoryWithScore(memory=memory, score=score)


@router.post("/{memory_id}/access", response_model=Memory)
def record_memory_access(memory_id: str) -> Memory:
    """Call this when a memory is actually used (e.g. an agent pulls
    it into context) -- this is the only thing that should feed the
    access-anomaly signal, deliberately kept separate from scoring."""
    memory = _store.record_access(memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return memory
