from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.memories import (
    create_memory, list_memories, get_memory_score, record_memory_access, MemoryCreate, _store,
)
from app.models.memory import Memory, MemoryCategory
from app.core.contradiction import ContradictionResult, MemoryRelationship

# NOTE: these tests call the route functions directly (create_memory(),
# list_memories(), get_memory_score()) instead of going through
# fastapi.testclient.TestClient. The installed starlette version here
# requires a package called "httpx2" for TestClient that doesn't
# actually exist on PyPI as of writing -- an unrelated version
# mismatch, not something to work around by pinning things blindly.
# Calling the route functions directly still exercises everything that
# matters (store wiring, 404 handling, access recording, the real
# scoring pipeline) without depending on that broken import path.

USER = "test_user_api"
AGENT = "test_agent_api"


def _make(content, category=MemoryCategory.EMPLOYMENT, user_id=USER, agent_id=AGENT):
    return MemoryCreate(content=content, category=category, user_id=user_id, agent_id=agent_id)


def test_create_memory_generates_id_and_stores_fields():
    memory = create_memory(_make("User works at Google"))
    assert memory.id  # server-generated, non-empty
    assert memory.content == "User works at Google"
    assert memory.user_id == USER
    assert memory.agent_id == AGENT
    print(f"✓ create_memory() generated id {memory.id}")


def test_list_memories_scoped_by_user_and_agent():
    other_user, other_agent = "other_user_api", "other_agent_api"
    create_memory(_make("Memory in scope A", user_id=USER, agent_id=AGENT))
    create_memory(_make("Memory in scope B", user_id=other_user, agent_id=other_agent))

    scoped = list_memories(USER, AGENT)
    other_scoped = list_memories(other_user, other_agent)

    assert all(m.user_id == USER and m.agent_id == AGENT for m in scoped)
    assert all(m.user_id == other_user for m in other_scoped)
    print(f"✓ list_memories() isolates scopes ({len(scoped)} vs {len(other_scoped)})")


def test_get_score_for_unknown_id_raises_404():
    with pytest.raises(HTTPException) as exc_info:
        get_memory_score("no-such-memory-id")
    assert exc_info.value.status_code == 404
    print("✓ get_memory_score() on unknown id raises 404")


def test_get_score_does_not_increment_access_count():
    """Scoring is a read-only diagnostic check, not usage -- an
    audit/monitoring job that scores every memory must not silently
    suppress the access-anomaly signal for everything it touches."""
    memory = create_memory(_make("User lives in Chandigarh", category=MemoryCategory.LOCATION))
    get_memory_score(memory.id)
    get_memory_score(memory.id)
    assert _store.get(memory.id).access_count == 0
    print("✓ get_memory_score() leaves access_count untouched")


def test_record_memory_access_increments_count():
    memory = create_memory(_make("User lives in Mohali", category=MemoryCategory.LOCATION))
    updated = record_memory_access(memory.id)
    assert updated.access_count == 1

    updated_again = record_memory_access(memory.id)
    assert updated_again.access_count == 2
    print("✓ record_memory_access() increments access_count on every call")


def test_record_memory_access_for_unknown_id_raises_404():
    with pytest.raises(HTTPException) as exc_info:
        record_memory_access("no-such-memory-id")
    assert exc_info.value.status_code == 404
    print("✓ record_memory_access() on unknown id raises 404")


@patch("app.core.scorer.detect_contradiction")
def test_get_score_detects_contradiction_end_to_end(mock_detect):
    """
    Mocks only the Gemini network call (as test_scorer_phase2.py does)
    so the real retrieval + scoring pipeline runs underneath the API
    route, proving the route is wired to the actual scorer correctly.
    """
    mock_detect.return_value = ContradictionResult(
        relationship=MemoryRelationship.CONTRADICTS,
        score=0.9,
        reasoning="Mocked contradiction for API test.",
    )

    # score_memory_full() only checks candidates strictly newer than the
    # memory being scored (scorer.py line 44). MemoryCreate has no
    # created_at field, so two back-to-back create_memory() calls can
    # land on the same real-clock timestamp and neither would count as
    # "newer" -- seed explicit, unambiguous timestamps here instead,
    # the same way test_scorer_phase2.py does.
    now = datetime.utcnow()
    old_memory = Memory(
        id="contra_old", content="User works at Google", category=MemoryCategory.EMPLOYMENT,
        user_id="contra_user", agent_id="contra_agent", created_at=now,
    )
    newer_memory = Memory(
        id="contra_new", content="User now works at Microsoft", category=MemoryCategory.EMPLOYMENT,
        user_id="contra_user", agent_id="contra_agent", created_at=now + timedelta(days=1),
    )
    _store.add(old_memory)
    _store.add(newer_memory)

    result = get_memory_score(old_memory.id)
    assert result.score.contradiction_score == 0.9
    print(f"✓ get_memory_score() surfaces a real contradiction: {result.score.final_score}")