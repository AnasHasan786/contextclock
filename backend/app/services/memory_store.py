from datetime import datetime
from typing import Optional

from app.models.memory import Memory


class MemoryStore:
    """
    Simple in-memory repository for Memory objects.

    Memories are grouped by (user_id, agent_id) so retrieval/scoring
    only ever looks at memories from the correct scope. This is not
    persistent across restarts -- swap for a database-backed store
    later without changing the interface used by services/routes.
    """

    def __init__(self) -> None:
        self._memories: dict[str, Memory] = {}

    def add(self, memory: Memory) -> Memory:
        self._memories[memory.id] = memory
        return memory

    def get(self, memory_id: str) -> Optional[Memory]:
        return self._memories.get(memory_id)

    def list_for_scope(self, user_id: str, agent_id: str) -> list[Memory]:
        return [
            m for m in self._memories.values()
            if m.user_id == user_id and m.agent_id == agent_id
        ]

    def record_access(self, memory_id: str) -> Optional[Memory]:
        """
        Bumps access_count and last_accessed_at for a memory.
        Call this whenever a memory is read/retrieved, so the
        access-anomaly signal reflects real usage.
        """
        memory = self._memories.get(memory_id)
        if memory is None:
            return None
        memory.access_count += 1
        memory.last_accessed_at = datetime.utcnow()
        return memory