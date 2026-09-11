import pytest

from app.evaluation.metrics import (
    summarize_distribution,
    detection_rate,
    detection_rates_at_standard_thresholds,
    STANDARD_THRESHOLDS,
)


def test_summarize_distribution_basic_stats():
    summary = summarize_distribution([0.2, 0.4, 0.6, 0.8, 1.0])

    assert summary.n == 5
    assert summary.mean == 0.6
    assert summary.median == 0.6
    assert summary.minimum == 0.2
    assert summary.maximum == 1.0
    assert summary.stdev > 0.0


def test_summarize_distribution_single_value_has_zero_stdev():
    summary = summarize_distribution([0.5])

    assert summary.n == 1
    assert summary.stdev == 0.0


def test_summarize_distribution_raises_on_empty_list():
    with pytest.raises(ValueError):
        summarize_distribution([])


def test_detection_rate_counts_scores_meeting_or_exceeding_threshold():
    scores = [0.1, 0.3, 0.3, 0.7, 0.9]

    result = detection_rate(scores, threshold=0.3)

    assert result.detected == 4  # 0.3, 0.3, 0.7, 0.9
    assert result.total == 5
    assert result.rate == 0.8


def test_detection_rate_raises_on_empty_list():
    with pytest.raises(ValueError):
        detection_rate([], threshold=0.5)


def test_detection_rates_at_standard_thresholds_covers_all_three_levels():
    scores = [0.1, 0.35, 0.65, 0.85]

    results = detection_rates_at_standard_thresholds(scores)

    assert set(results.keys()) == {"AGING", "STALE", "EXPIRED"}
    assert results["AGING"].threshold == STANDARD_THRESHOLDS["AGING"]
    assert results["AGING"].detected == 3   # 0.35, 0.65, 0.85
    assert results["STALE"].detected == 2   # 0.65, 0.85
    assert results["EXPIRED"].detected == 1  # 0.85