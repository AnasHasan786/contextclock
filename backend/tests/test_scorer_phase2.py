from datetime import datetime
from unittest.mock import patch

from app.models.memory import Memory, MemoryCategory, StalenessLevel
from app.core.contradiction import ContradictionResult, MemoryRelationship
from app.core.scorer import resolve_contradiction_score, score_memory_full


def make_memory(id, content, category=MemoryCategory.EMPLOYMENT, created_at=None):
    return Memory(
        id=id, content=content, category=category,
        user_id="u1", agent_id="a1",
        created_at=created_at or datetime(2026, 1, 1),
    )


def test_no_newer_candidates_returns_zero():
    memory = make_memory("1", "User works at Google.", created_at=datetime(2026, 8, 1))
    older_memory = make_memory("0", "User was a student.", created_at=datetime(2020, 1, 1))

    score, reasoning = resolve_contradiction_score(memory, [memory, older_memory])

    assert score == 0.0
    assert "no newer" in reasoning.lower()


@patch("app.core.scorer.detect_contradiction")
def test_older_candidates_are_never_sent_to_gemini(mock_detect):
    memory = make_memory("1", "User works at Google.", created_at=datetime(2026, 8, 1))
    older_memory = make_memory(
        "0", "User is employed at Google.", created_at=datetime(2020, 1, 1)
    )

    resolve_contradiction_score(memory, [memory, older_memory])

    mock_detect.assert_not_called()


@patch("app.core.scorer.detect_contradiction")
def test_contradiction_score_propagates(mock_detect):
    mock_detect.return_value = ContradictionResult(
        relationship=MemoryRelationship.CONTRADICTS,
        score=0.9,
        reasoning="Mocked contradiction.",
    )

    old_memory = make_memory("1", "User works at Google.", created_at=datetime(2026, 1, 1))
    new_memory = make_memory("2", "User now works at Microsoft.", created_at=datetime(2026, 8, 1))

    score, reasoning = resolve_contradiction_score(old_memory, [old_memory, new_memory])

    assert score == 0.9
    assert "CONTRADICTS" in reasoning


@patch("app.core.scorer.detect_contradiction")
def test_takes_max_score_across_multiple_candidates(mock_detect):
    weak = ContradictionResult(
        relationship=MemoryRelationship.CONTRADICTS, score=0.4, reasoning="weak signal"
    )
    strong = ContradictionResult(
        relationship=MemoryRelationship.SUPERSEDES, score=0.9, reasoning="strong signal"
    )
    # Two calls happen (two newer candidates) -- return weak first, strong second.
    mock_detect.side_effect = [weak, strong]

    old_memory = make_memory("1", "User works at Google.", created_at=datetime(2026, 1, 1))
    candidate_a = make_memory("2", "User works at Alphabet.", created_at=datetime(2026, 3, 1))
    candidate_b = make_memory("3", "User works at Microsoft.", created_at=datetime(2026, 8, 1))

    score, reasoning = resolve_contradiction_score(
        old_memory, [old_memory, candidate_a, candidate_b]
    )

    assert score == 0.9
    assert "strong signal" in reasoning


@patch("app.core.scorer.detect_contradiction")
def test_unrelated_and_consistent_do_not_count(mock_detect):
    mock_detect.return_value = ContradictionResult(
        relationship=MemoryRelationship.UNRELATED, score=0.8, reasoning="irrelevant high score"
    )

    old_memory = make_memory("1", "User works at Google.", created_at=datetime(2026, 1, 1))
    new_memory = make_memory("2", "User enjoys hiking.", created_at=datetime(2026, 8, 1))

    score, reasoning = resolve_contradiction_score(old_memory, [old_memory, new_memory])

    # Even though the mocked score is 0.8, UNRELATED must not count --
    # only CONTRADICTS/SUPERSEDES should ever push the score up.
    assert score == 0.0


@patch("app.core.scorer.detect_contradiction")
def test_score_memory_full_reaches_expired(mock_detect):
    """
    Regression test locking in the manually-verified result: an old,
    unaccessed, genuinely-contradicted memory should reach EXPIRED --
    proving Phase 1's ~0.70 ceiling is broken once Phase 2 is wired in.
    """
    mock_detect.return_value = ContradictionResult(
        relationship=MemoryRelationship.CONTRADICTS,
        score=0.95,
        reasoning="Mocked strong contradiction.",
    )

    very_old_memory = make_memory("3", "User works at Google.", created_at=datetime(2024, 6, 1))
    newer_memory = make_memory("4", "User now works at Microsoft.", created_at=datetime(2026, 8, 27))

    result = score_memory_full(very_old_memory, [very_old_memory, newer_memory])

    assert result.staleness_level == StalenessLevel.EXPIRED
    assert result.final_score >= 0.80
    assert "Contradiction detail" in result.explanation