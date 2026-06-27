from app.models.memory import Memory, StalenessScore, MemoryCategory, StalenessLevel
from datetime import datetime


def test_memory_creation():
    memory = Memory(
        id="mem_001",
        content="User works at Google as a Software Engineer",
        category=MemoryCategory.EMPLOYMENT,
        user_id="user_123",
        agent_id="agent_abc",
    )
    assert memory.content == "User works at Google as a Software Engineer"
    assert memory.access_count == 0
    assert memory.category == MemoryCategory.EMPLOYMENT
    print("✓ Memory model works")


def test_staleness_score_creation():
    score = StalenessScore(
        memory_id="mem_001",
        time_decay_score=0.7,
        contradiction_score=0.4,
        access_anomaly_score=0.2,
        final_score=0.72,
        staleness_level=StalenessLevel.STALE,
        explanation="Memory is 8 months old and category 'employment' decays fast",
    )
    assert score.final_score == 0.72
    assert score.staleness_level == StalenessLevel.STALE
    print("✓ StalenessScore model works")


def test_defaults():
    memory = Memory(
        id="mem_002",
        content="User lives in Delhi",
        category=MemoryCategory.LOCATION,
        user_id="user_123",
        agent_id="agent_abc",
    )
    assert memory.access_count == 0
    assert memory.last_accessed_at is None
    assert isinstance(memory.created_at, datetime)
    print("✓ Defaults work correctly")
