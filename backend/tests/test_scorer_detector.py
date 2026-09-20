from types import SimpleNamespace
from unittest.mock import patch

from app.core.contradiction import ContradictionResult, MemoryRelationship
from app.core.scorer import resolve_contradiction_score, score_memory_full
from app.models.memory import Memory, MemoryCategory
from app.services.contradiction_cache import ContradictionCache


def _mem(memory_id: str) -> Memory:
    return Memory(
        id=memory_id,
        content=f"content {memory_id}",
        category=MemoryCategory.EMPLOYMENT,
        user_id="u1",
        agent_id="a1",
    )


def _verdict(score: float = 0.9) -> ContradictionResult:
    return ContradictionResult(
        relationship=MemoryRelationship.CONTRADICTS,
        score=score,
        reasoning="incompatible claims",
    )


def _candidates(new: Memory):
    # Stand-in for find_candidate_memories(): avoids loading embeddings.
    return patch(
        "app.core.scorer.find_candidate_memories",
        return_value=[SimpleNamespace(memory=new)],
    )


def test_custom_detector_is_used():
    old, new = _mem("old"), _mem("new")
    calls = []

    def fake_detector(old_memory, new_memory):
        calls.append((old_memory.id, new_memory.id))
        return _verdict(0.9)

    with _candidates(new):
        score, reasoning = resolve_contradiction_score(
            old, [old, new], detector=fake_detector
        )

    assert calls == [("old", "new")]
    assert score == 0.9
    assert "[CONTRADICTS]" in reasoning


def test_default_detector_is_still_detect_contradiction():
    old, new = _mem("old"), _mem("new")
    with _candidates(new), patch(
        "app.core.scorer.detect_contradiction", return_value=_verdict(0.8)
    ) as mock_detect:
        score, _ = resolve_contradiction_score(old, [old, new])

    assert mock_detect.call_count == 1
    assert score == 0.8


def test_score_memory_full_passes_detector_through():
    old, new = _mem("old"), _mem("new")

    def fake_detector(old_memory, new_memory):
        return _verdict(0.9)

    with _candidates(new):
        result = score_memory_full(old, [old, new], detector=fake_detector)

    assert result.contradiction_score == 0.9


def test_empty_cache_is_used_and_second_score_makes_no_new_call():
    """An empty ContradictionCache is falsy (len 0); it must still be used."""
    old, new = _mem("old"), _mem("new")
    cache = ContradictionCache()
    assert len(cache) == 0

    with _candidates(new), patch(
        "app.services.contradiction_cache.detect_contradiction",
        return_value=_verdict(),
    ) as cache_detect, patch("app.core.scorer.detect_contradiction") as scorer_detect:
        resolve_contradiction_score(old, [old, new], detector=cache)
        resolve_contradiction_score(old, [old, new], detector=cache)

    assert cache_detect.call_count == 1
    scorer_detect.assert_not_called()
    assert len(cache) == 1