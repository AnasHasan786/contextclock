from unittest.mock import MagicMock, patch

from app.core.contradiction import ContradictionResult, MemoryRelationship
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


def _verdict(score: float = 0.95) -> ContradictionResult:
    return ContradictionResult(
        relationship=MemoryRelationship.CONTRADICTS,
        score=score,
        reasoning="incompatible claims",
    )


def test_same_pair_calls_gemini_once():
    cache = ContradictionCache()
    old, new = _mem("old"), _mem("new")
    with patch(
        "app.services.contradiction_cache.detect_contradiction",
        return_value=_verdict(),
    ) as mock_detect:
        first = cache(old, new)
        second = cache(old, new)

    assert mock_detect.call_count == 1
    assert first == second
    assert len(cache) == 1


def test_different_pairs_are_cached_separately():
    cache = ContradictionCache()
    with patch(
        "app.services.contradiction_cache.detect_contradiction",
        return_value=_verdict(),
    ) as mock_detect:
        cache(_mem("a"), _mem("b"))
        cache(_mem("a"), _mem("c"))

    assert mock_detect.call_count == 2
    assert len(cache) == 2


def test_api_failure_is_not_cached():
    """Runs the real detect_contradiction() fallback path, so this also
    fails if the fallback message is ever reworded."""
    cache = ContradictionCache()
    with patch("app.core.contradiction._client") as mock_client:
        mock_client.models.generate_content.side_effect = RuntimeError("boom")
        result = cache(_mem("old"), _mem("new"))

    assert result.relationship == MemoryRelationship.UNRELATED
    assert result.reasoning.startswith("API call failed")
    assert len(cache) == 0


def test_unparseable_response_is_not_cached():
    cache = ContradictionCache()
    with patch("app.core.contradiction._client") as mock_client:
        mock_client.models.generate_content.return_value = MagicMock(
            parsed=None, text="junk"
        )
        result = cache(_mem("old"), _mem("new"))

    assert result.reasoning.startswith("Response did not parse to schema")
    assert len(cache) == 0


def test_recovers_after_failure():
    cache = ContradictionCache()
    fallback = ContradictionResult(
        relationship=MemoryRelationship.UNRELATED,
        score=0.0,
        reasoning="API call failed: RuntimeError: boom",
    )
    old, new = _mem("old"), _mem("new")
    with patch(
        "app.services.contradiction_cache.detect_contradiction",
        side_effect=[fallback, _verdict()],
    ) as mock_detect:
        cache(old, new)  # fails, not cached
        cache(old, new)  # succeeds, cached
        cache(old, new)  # served from cache

    assert mock_detect.call_count == 2
    assert len(cache) == 1