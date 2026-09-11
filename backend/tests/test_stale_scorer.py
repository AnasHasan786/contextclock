from datetime import datetime, timezone
from unittest.mock import patch

from app.models.memory import MemoryCategory, StalenessLevel
from app.core.contradiction import ContradictionResult, MemoryRelationship
from app.evaluation.stale_scorer import score_stale_pair, STALE_EVAL_WEIGHTS


def test_weights_sum_to_one_and_preserve_original_ratio():
    """
    access_anomaly is excluded (see module docstring), so the two
    remaining signals must sum to exactly 1.0, and must preserve the
    original 50:30 ratio between time_decay and contradiction from
    scorer.py's production WEIGHTS.
    """
    assert STALE_EVAL_WEIGHTS["time_decay"] + STALE_EVAL_WEIGHTS["contradiction"] == 1.0
    assert round(STALE_EVAL_WEIGHTS["time_decay"] / STALE_EVAL_WEIGHTS["contradiction"], 4) == round(0.50 / 0.30, 4)


@patch("app.evaluation.stale_scorer.detect_contradiction")
def test_score_combines_time_decay_and_contradiction_with_reweighted_values(mock_detect):
    mock_detect.return_value = ContradictionResult(
        relationship=MemoryRelationship.CONTRADICTS,
        score=0.8,
        reasoning="Mocked contradiction.",
    )

    # LOCATION half-life is 365 days; a 365-day gap gives a known,
    # exactly-reproducible time_decay of 0.5 (one half-life elapsed).
    old_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    new_ts = datetime(2025, 1, 1, tzinfo=timezone.utc)  # 366 days, close enough to 1 half-life

    result = score_stale_pair(
        m_old="User lives in Delhi.",
        m_new="User moved to Chandigarh.",
        category=MemoryCategory.LOCATION,
        old_timestamp=old_ts,
        new_timestamp=new_ts,
    )

    expected_final = round(
        STALE_EVAL_WEIGHTS["time_decay"] * result.time_decay_score
        + STALE_EVAL_WEIGHTS["contradiction"] * 0.8,
        4,
    )
    assert result.contradiction_score == 0.8
    assert result.access_anomaly_score == 0.0
    assert result.final_score == expected_final


@patch("app.evaluation.stale_scorer.detect_contradiction")
def test_unrelated_relationship_contributes_zero_contradiction(mock_detect):
    """
    Even if the LLM returns a nonzero score, UNRELATED/CONSISTENT
    relationships must not count toward the contradiction signal --
    mirrors resolve_contradiction_score()'s logic in scorer.py.
    """
    mock_detect.return_value = ContradictionResult(
        relationship=MemoryRelationship.UNRELATED,
        score=0.9,
        reasoning="Mocked unrelated result with a high but irrelevant score.",
    )

    result = score_stale_pair(
        m_old="User likes coffee.",
        m_new="User lives in Chandigarh.",
        category=MemoryCategory.PREFERENCE,
        old_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        new_timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )

    assert result.contradiction_score == 0.0


@patch("app.evaluation.stale_scorer.detect_contradiction")
def test_expired_is_reachable_with_only_two_signals(mock_detect):
    """
    With access_anomaly excluded and weights renormalized to sum to
    1.0, EXPIRED (>=0.80) must still be reachable via time_decay and
    contradiction alone -- this was the whole point of reweighting
    instead of forcing access_anomaly to 0.0 under the original
    (0.50/0.30/0.20) weights, which would cap the max score at 0.80.
    """
    mock_detect.return_value = ContradictionResult(
        relationship=MemoryRelationship.CONTRADICTS,
        score=1.0,
        reasoning="Mocked maximal contradiction.",
    )

    # EMPLOYMENT half-life is 180 days; a ~900-day gap (5 half-lives)
    # drives time_decay to ~0.97, effectively saturating at 1.0.
    result = score_stale_pair(
        m_old="User works at Google.",
        m_new="User now works at Microsoft.",
        category=MemoryCategory.EMPLOYMENT,
        old_timestamp=datetime(2022, 1, 1, tzinfo=timezone.utc),
        new_timestamp=datetime(2024, 6, 15, tzinfo=timezone.utc),
    )

    assert result.staleness_level == StalenessLevel.EXPIRED


@patch("app.evaluation.stale_scorer.detect_contradiction")
def test_model_override_is_forwarded_to_detect_contradiction(mock_detect):
    mock_detect.return_value = ContradictionResult(
        relationship=MemoryRelationship.CONSISTENT,
        score=0.1,
        reasoning="Mocked reasoning.",
    )

    score_stale_pair(
        m_old="User works at Google.",
        m_new="User still works at Google.",
        category=MemoryCategory.EMPLOYMENT,
        old_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        new_timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        model="gemini-3.5-flash-lite",
    )

    _, kwargs = mock_detect.call_args
    assert kwargs["model"] == "gemini-3.5-flash-lite"