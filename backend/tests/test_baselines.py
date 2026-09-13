from datetime import datetime
from unittest.mock import patch, MagicMock

from app.models.memory import Memory, MemoryCategory
from app.core.baselines import always_llm_score
from app.core.contradiction import ContradictionResult, MemoryRelationship


def make_memory(id, content, created_at, category=MemoryCategory.EMPLOYMENT):
    return Memory(
        id=id, content=content, category=category,
        user_id="u1", agent_id="a1", created_at=created_at,
    )


@patch("app.core.baselines.detect_contradiction")
def test_default_model_is_used_when_not_overridden(mock_detect):
    mock_detect.return_value = ContradictionResult(
        relationship=MemoryRelationship.CONTRADICTS, score=0.9, reasoning="mocked",
    )
    old = make_memory("1", "Works at Google.", datetime(2024, 1, 1))
    new = make_memory("2", "Now works at Microsoft.", datetime(2024, 6, 1))

    always_llm_score(old, [old, new])

    _, kwargs = mock_detect.call_args
    assert kwargs["model"] == "gemini-3.6-flash"


@patch("app.core.baselines.detect_contradiction")
def test_model_override_is_passed_through(mock_detect):
    """
    The STALE evaluation runner needs this baseline to use the
    eval-tier model, same as detect_contradiction() and
    classify_memory_category() -- otherwise this baseline alone would
    exceed gemini-3.6-flash's 20/day free-tier cap over 400 rows,
    since it makes one call per candidate with no retrieval filtering.
    """
    mock_detect.return_value = ContradictionResult(
        relationship=MemoryRelationship.CONTRADICTS, score=0.9, reasoning="mocked",
    )
    old = make_memory("1", "Works at Google.", datetime(2024, 1, 1))
    new = make_memory("2", "Now works at Microsoft.", datetime(2024, 6, 1))

    always_llm_score(old, [old, new], model="gemini-3.5-flash-lite")

    _, kwargs = mock_detect.call_args
    assert kwargs["model"] == "gemini-3.5-flash-lite"


@patch("app.core.baselines.detect_contradiction")
def test_model_override_applies_to_every_candidate_checked(mock_detect):
    mock_detect.return_value = ContradictionResult(
        relationship=MemoryRelationship.UNRELATED, score=0.0, reasoning="mocked",
    )
    old = make_memory("1", "Works at Google.", datetime(2024, 1, 1))
    candidate_a = make_memory("2", "Something else.", datetime(2024, 3, 1))
    candidate_b = make_memory("3", "Now works at Microsoft.", datetime(2024, 6, 1))

    always_llm_score(old, [old, candidate_a, candidate_b], model="gemini-3.5-flash-lite")

    assert mock_detect.call_count == 2
    for call in mock_detect.call_args_list:
        assert call.kwargs["model"] == "gemini-3.5-flash-lite"