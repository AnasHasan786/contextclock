from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional

class MemoryCategory(str, Enum):
    """
    How fast a memory decays depends on its category.
    Job title changes faster than favourite colour.
    """
    EMPLOYMENT="employment"
    LOCATION="location"
    RELATIONSHIP="relationship"
    PREFERENCE="preference"
    PERSONAL="personal"
    FACT="fact"

class StalenessLevel(str, Enum):
    FRESH="fresh"
    AGING="aging"
    STALE="stale"
    EXPIRED="expired"

class Memory(BaseModel):
    """
    Represents a single memory entry stored by an AI agent.
    """
    id: str
    content: str
    category: MemoryCategory
    user_id: str
    agent_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed_at: Optional[datetime] = None
    access_count: int = 0

class StalenessScore(BaseModel):
    """
    The staleness assessment for a single memory.
    Three signals combined into one score.
    """
    memory_id: str
    time_decay_score: float = 0.0
    contradiction_score: float = 0.0
    access_anomaly_score: float = 0.0
    final_score: float = 0.0
    staleness_level: StalenessLevel = StalenessLevel.FRESH
    computed_at: datetime = Field(default_factory=datetime.utcnow)
    explanation: str = ""

class MemoryWithScore(BaseModel):
    """
    A memory bundled with its current staleness score.
    This is what the dashboard and API will serve.
    """
    memory: Memory
    score: StalenessScore

class LatestScoreRecord(BaseModel):
    """Wrapper so the bulk endpoint can tell 'never checked' (key absent)
    apart from 'checked before, might be outdated now' (key present)."""
    memory: Memory
    score: StalenessScore