from datetime import datetime
from unittest.mock import patch, MagicMock

from app.models.memory import Memory, MemoryCategory
from app.core.contradiction import (
    detect_contradiction,
    ContradictionResult,
    MemoryRelationship,
)


def make_memory(id, content, category=MemoryCategory.EMPLOYMENT):
    return Memory(
        id=id, content=content, category=category,
        user_id="u1", agent_id="a1", created_at=datetime(2026, 1, 1),
    )


# All tests mock app.core.contradiction._client so no real network
# calls happen and the test suite has zero API cost / no network
# dependency, per Step 8 design decision.

@patch("app.core.contradiction._client")
def test_successful_response_returns_parsed_result(mock_client):
    expected = ContradictionResult(
        relationship=MemoryRelationship.CONTRADICTS,
        score=0.9,
        reasoning="Mocked reasoning.",
    )
    mock_response = MagicMock()
    mock_response.parsed = expected
    mock_client.models.generate_content.return_value = mock_response

    old = make_memory("1", "User works at Google.")
    new = make_memory("2", "User now works at Microsoft.")

    result = detect_contradiction(old, new)

    assert result == expected
    mock_client.models.generate_content.assert_called_once()


@patch("app.core.contradiction._client")
def test_default_model_is_used_when_not_overridden(mock_client):
    expected = ContradictionResult(
        relationship=MemoryRelationship.CONSISTENT,
        score=0.1,
        reasoning="Mocked reasoning.",
    )
    mock_response = MagicMock()
    mock_response.parsed = expected
    mock_client.models.generate_content.return_value = mock_response

    old = make_memory("1", "User works at Google.")
    new = make_memory("2", "User still works at Google.")

    detect_contradiction(old, new)

    _, kwargs = mock_client.models.generate_content.call_args
    assert kwargs["model"] == "gemini-3.6-flash"


@patch("app.core.contradiction._client")
def test_model_override_is_passed_through(mock_client):
    """
    Evaluation code (the STALE evaluation runner) passes a different
    model than the production default, per the same disclosed
    deviation already applied to classify_memory_category().
    """
    expected = ContradictionResult(
        relationship=MemoryRelationship.CONSISTENT,
        score=0.1,
        reasoning="Mocked reasoning.",
    )
    mock_response = MagicMock()
    mock_response.parsed = expected
    mock_client.models.generate_content.return_value = mock_response

    old = make_memory("1", "User works at Google.")
    new = make_memory("2", "User still works at Google.")

    detect_contradiction(old, new, model="gemini-3.5-flash-lite")

    _, kwargs = mock_client.models.generate_content.call_args
    assert kwargs["model"] == "gemini-3.5-flash-lite"


@patch("app.core.contradiction._client")
def test_api_exception_triggers_safe_fallback(mock_client):
    mock_client.models.generate_content.side_effect = Exception("simulated network failure")

    old = make_memory("1", "User works at Google.")
    new = make_memory("2", "User now works at Microsoft.")

    result = detect_contradiction(old, new)

    assert result.relationship == MemoryRelationship.UNRELATED
    assert result.score == 0.0
    assert "API call failed" in result.reasoning


@patch("app.core.contradiction._client")
def test_unparseable_response_triggers_safe_fallback(mock_client):
    mock_response = MagicMock()
    mock_response.parsed = None
    mock_response.text = "not valid json"
    mock_client.models.generate_content.return_value = mock_response

    old = make_memory("1", "User works at Google.")
    new = make_memory("2", "User now works at Microsoft.")

    result = detect_contradiction(old, new)

    assert result.relationship == MemoryRelationship.UNRELATED
    assert result.score == 0.0
    assert "did not parse" in result.reasoning.lower()


@patch("app.core.contradiction._client")
def test_fallback_never_raises(mock_client):
    """
    The core safety guarantee of Step 6: no matter what goes wrong,
    detect_contradiction must return a ContradictionResult, never
    propagate an exception to the caller.
    """
    mock_client.models.generate_content.side_effect = RuntimeError("anything")

    old = make_memory("1", "User works at Google.")
    new = make_memory("2", "User now works at Microsoft.")

    try:
        result = detect_contradiction(old, new)
    except Exception as e:
        assert False, f"detect_contradiction raised an exception: {e}"

    assert isinstance(result, ContradictionResult)