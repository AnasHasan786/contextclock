from unittest.mock import patch, MagicMock

from app.models.memory import MemoryCategory
from app.core.category_classifier import (
    classify_memory_category,
    CategoryClassificationResult,
    FALLBACK_CATEGORY,
    MODEL_NAME,
)


# All tests mock app.core.category_classifier._client so no real
# network calls happen and the test suite has zero API cost / no
# network dependency, matching the convention in test_contradiction.py.

@patch("app.core.category_classifier._client")
def test_default_model_is_used_when_not_overridden(mock_client):
    mock_response = MagicMock()
    mock_response.parsed = CategoryClassificationResult(
        category=MemoryCategory.FACT, confidence=0.9, reasoning="Mocked reasoning."
    )
    mock_client.models.generate_content.return_value = mock_response

    classify_memory_category(content="Some memory content.")

    _, kwargs = mock_client.models.generate_content.call_args
    assert kwargs["model"] == MODEL_NAME


@patch("app.core.category_classifier._client")
def test_model_override_is_passed_through(mock_client):
    """
    Evaluation code (build_stale_dataset.py) passes a different model
    to work around gemini-3.6-flash's restrictive free-tier daily
    quota. This must actually reach the API call, not be silently
    ignored in favor of MODEL_NAME.
    """
    mock_response = MagicMock()
    mock_response.parsed = CategoryClassificationResult(
        category=MemoryCategory.FACT, confidence=0.9, reasoning="Mocked reasoning."
    )
    mock_client.models.generate_content.return_value = mock_response

    classify_memory_category(content="Some memory content.", model="gemini-3.5-flash-lite")

    _, kwargs = mock_client.models.generate_content.call_args
    assert kwargs["model"] == "gemini-3.5-flash-lite"


@patch("app.core.category_classifier._client")
def test_successful_response_returns_parsed_result(mock_client):
    expected = CategoryClassificationResult(
        category=MemoryCategory.LOCATION,
        confidence=0.95,
        reasoning="Mocked reasoning.",
    )
    mock_response = MagicMock()
    mock_response.parsed = expected
    mock_client.models.generate_content.return_value = mock_response

    result = classify_memory_category(
        content="I've been based in Seattle for the last few years.",
        related_content="I just moved to Austin.",
    )

    assert result == expected
    mock_client.models.generate_content.assert_called_once()


@patch("app.core.category_classifier._client")
def test_single_content_without_related_still_calls_api(mock_client):
    """
    classify_memory_category must work with related_content=None
    (single-memory classification, for future production use where
    a new memory is stored without a counterpart to compare against).
    """
    expected = CategoryClassificationResult(
        category=MemoryCategory.PERSONAL,
        confidence=0.9,
        reasoning="Mocked reasoning.",
    )
    mock_response = MagicMock()
    mock_response.parsed = expected
    mock_client.models.generate_content.return_value = mock_response

    result = classify_memory_category(content="My birthday is June 3rd.")

    assert result == expected
    mock_client.models.generate_content.assert_called_once()


@patch("app.core.category_classifier._client")
def test_api_exception_triggers_safe_fallback(mock_client):
    mock_client.models.generate_content.side_effect = Exception("simulated network failure")

    result = classify_memory_category(
        content="I've been based in Seattle for the last few years.",
        related_content="I just moved to Austin.",
    )

    assert result.category == FALLBACK_CATEGORY
    assert result.confidence == 0.0
    assert "API call failed" in result.reasoning


@patch("app.core.category_classifier._client")
def test_unparseable_response_triggers_safe_fallback(mock_client):
    mock_response = MagicMock()
    mock_response.parsed = None
    mock_response.text = "not valid json"
    mock_client.models.generate_content.return_value = mock_response

    result = classify_memory_category(
        content="I've been based in Seattle for the last few years.",
        related_content="I just moved to Austin.",
    )

    assert result.category == FALLBACK_CATEGORY
    assert result.confidence == 0.0
    assert "did not parse" in result.reasoning.lower()


@patch("app.core.category_classifier._client")
def test_fallback_never_raises(mock_client):
    """
    Core safety guarantee, mirroring test_fallback_never_raises in
    test_contradiction.py: no matter what goes wrong,
    classify_memory_category must return a CategoryClassificationResult,
    never propagate an exception to the caller.
    """
    mock_client.models.generate_content.side_effect = RuntimeError("anything")

    try:
        result = classify_memory_category(
            content="I've been based in Seattle for the last few years.",
            related_content="I just moved to Austin.",
        )
    except Exception as e:
        assert False, f"classify_memory_category raised an exception: {e}"

    assert isinstance(result, CategoryClassificationResult)