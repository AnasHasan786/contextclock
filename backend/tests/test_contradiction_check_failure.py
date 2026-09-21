from types import SimpleNamespace
from unittest.mock import patch

from app.core.contradiction import ContradictionResult, MemoryRelationship
from app.core.fallback import CHECK_INCOMPLETE_PREFIX, is_fallback
from app.core.scorer import resolve_contradiction_score, score_memory_full
from app.models.memory import Memory, MemoryCategory


def _mem(memory_id: str) -> Memory:
    return Memory(
        id=memory_id,
        content=f"content {memory_id}",
        category=MemoryCategory.EMPLOYMENT,
        user_id="u1",
        agent_id="a1",
    )


def _result(
    relationship: MemoryRelationship, score: float, reasoning: str
) -> ContradictionResult:
    return ContradictionResult(
        relationship=relationship, score=score, reasoning=reasoning
    )


FAILED = _result(
    MemoryRelationship.UNRELATED, 0.0, "API call failed: ServerError: 503 UNAVAILABLE"
)


def _candidates(*memories: Memory):
    # Stand-in for find_candidate_memories(): avoids loading embeddings.
    return patch(
        "app.core.scorer.find_candidate_memories",
        return_value=[SimpleNamespace(memory=m) for m in memories],
    )


def test_fallback_messages_are_recognized():
    assert is_fallback(FAILED)
    assert is_fallback(
        _result(
            MemoryRelationship.UNRELATED,
            0.0,
            "Response did not parse to schema. Raw: None",
        )
    )


def test_normal_reasoning_is_not_a_fallback():
    assert not is_fallback(
        _result(
            MemoryRelationship.CONTRADICTS,
            0.9,
            "The newer memory replaces the older one.",
        )
    )


def test_failed_lookup_with_no_contradiction_is_reported():
    """Runs the real detect_contradiction() failure path."""
    old, new = _mem("old"), _mem("new")
    with _candidates(new), patch("app.core.contradiction._client") as client:
        client.models.generate_content.side_effect = RuntimeError("boom")
        score, reasoning = resolve_contradiction_score(old, [old, new])

    assert score == 0.0
    assert reasoning.startswith(CHECK_INCOMPLETE_PREFIX)
    assert "1 of 1" in reasoning
    assert "boom" in reasoning


def test_every_failed_comparison_is_counted():
    old, a, b = _mem("old"), _mem("a"), _mem("b")

    def detector(old_memory, new_memory):
        return FAILED

    with _candidates(a, b):
        score, reasoning = resolve_contradiction_score(
            old, [old, a, b], detector=detector
        )

    assert score == 0.0
    assert reasoning.startswith(CHECK_INCOMPLETE_PREFIX)
    assert "2 of 2" in reasoning


def test_real_contradiction_wins_over_a_failed_sibling():
    old, a, b = _mem("old"), _mem("a"), _mem("b")
    results = iter(
        [FAILED, _result(MemoryRelationship.CONTRADICTS, 0.9, "clear conflict")]
    )

    def detector(old_memory, new_memory):
        return next(results)

    with _candidates(a, b):
        score, reasoning = resolve_contradiction_score(
            old, [old, a, b], detector=detector
        )

    assert score == 0.9
    assert "[CONTRADICTS]" in reasoning
    assert not reasoning.startswith(CHECK_INCOMPLETE_PREFIX)


def test_successful_unrelated_verdicts_are_not_reported_as_failures():
    old, new = _mem("old"), _mem("new")

    def detector(old_memory, new_memory):
        return _result(MemoryRelationship.UNRELATED, 0.0, "Different topics.")

    with _candidates(new):
        score, reasoning = resolve_contradiction_score(
            old, [old, new], detector=detector
        )

    assert score == 0.0
    assert reasoning == "No contradiction or supersession detected among candidates."


def test_incomplete_check_reaches_the_score_explanation():
    old, new = _mem("old"), _mem("new")

    def detector(old_memory, new_memory):
        return FAILED

    with _candidates(new):
        result = score_memory_full(old, [old, new], detector=detector)

    assert result.contradiction_score == 0.0
    assert CHECK_INCOMPLETE_PREFIX in result.explanation
