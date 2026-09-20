from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.api import memories as memories_api
from app.api.memories import MemoryCreate, create_memory, get_memory_score
from app.core.contradiction import ContradictionResult, MemoryRelationship
from app.models.memory import MemoryCategory
from app.services.contradiction_cache import ContradictionCache
from app.services.memory_store import MemoryStore


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(memories_api, "_store", MemoryStore())
    monkeypatch.setattr(memories_api, "_contradiction_cache", ContradictionCache())


def _create(content: str):
    return create_memory(
        MemoryCreate(
            content=content,
            category=MemoryCategory.EMPLOYMENT,
            user_id="u1",
            agent_id="a1",
        )
    )


def _verdict(score: float = 0.9) -> ContradictionResult:
    return ContradictionResult(
        relationship=MemoryRelationship.CONTRADICTS,
        score=score,
        reasoning="incompatible claims",
    )


def _candidates(new):
    # Stand-in for find_candidate_memories(): avoids loading embeddings.
    return patch(
        "app.core.scorer.find_candidate_memories",
        return_value=[SimpleNamespace(memory=new)],
    )


def test_scoring_same_memory_twice_calls_gemini_once():
    old = _create("User works at Google")
    new = _create("User now works at Microsoft")

    with _candidates(new), patch(
        "app.services.contradiction_cache.detect_contradiction",
        return_value=_verdict(0.9),
    ) as mock_detect:
        first = get_memory_score(old.id)
        second = get_memory_score(old.id)

    assert mock_detect.call_count == 1
    assert first.score.contradiction_score == 0.9
    assert second.score.contradiction_score == 0.9


def test_failed_lookup_is_retried_on_next_score_request():
    old = _create("User works at Google")
    new = _create("User now works at Microsoft")
    fallback = ContradictionResult(
        relationship=MemoryRelationship.UNRELATED,
        score=0.0,
        reasoning="API call failed: RuntimeError: quota",
    )

    with _candidates(new), patch(
        "app.services.contradiction_cache.detect_contradiction",
        side_effect=[fallback, _verdict(0.9)],
    ) as mock_detect:
        first = get_memory_score(old.id)
        second = get_memory_score(old.id)

    assert mock_detect.call_count == 2
    assert first.score.contradiction_score == 0.0
    assert second.score.contradiction_score == 0.9