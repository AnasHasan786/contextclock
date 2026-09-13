import json
from datetime import datetime, timezone

import pytest

from app.models.memory import MemoryCategory
from app.evaluation.run_stale_eval import load_stale_records, aggregate_metrics


def _write_jsonl(tmp_path, rows):
    path = tmp_path / "stale_eval_sample.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return str(path)


def test_load_stale_records_parses_category_and_timestamps(tmp_path):
    rows = [
        {
            "uid": "abc123",
            "m_old": "User lives in Seattle.",
            "m_new": "User moved to Austin.",
            "conflict_type": "T1",
            "old_timestamp": "2021-06-15T10:30:00+00:00",
            "new_timestamp": "2023-06-15T10:30:00+00:00",
            "gap_days": 730,
            "category": "location",
            "category_confidence": 1.0,
        }
    ]
    path = _write_jsonl(tmp_path, rows)

    records = load_stale_records(path)

    assert len(records) == 1
    assert records[0]["category"] == MemoryCategory.LOCATION
    assert records[0]["old_timestamp"] == datetime(2021, 6, 15, 10, 30, tzinfo=timezone.utc)
    assert records[0]["new_timestamp"] == datetime(2023, 6, 15, 10, 30, tzinfo=timezone.utc)
    assert records[0]["uid"] == "abc123"


def test_load_stale_records_skips_blank_lines(tmp_path):
    rows = [
        {
            "uid": "abc123", "m_old": "a", "m_new": "b", "conflict_type": "T1",
            "old_timestamp": "2021-06-15T10:30:00+00:00",
            "new_timestamp": "2023-06-15T10:30:00+00:00",
            "category": "fact", "category_confidence": 0.9,
        }
    ]
    path = _write_jsonl(tmp_path, rows)
    # Inject a blank line into the file
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n")

    records = load_stale_records(path)
    assert len(records) == 1


def test_load_stale_records_raises_on_malformed_category(tmp_path):
    rows = [
        {
            "uid": "bad1", "m_old": "a", "m_new": "b", "conflict_type": "T1",
            "old_timestamp": "2021-06-15T10:30:00+00:00",
            "new_timestamp": "2023-06-15T10:30:00+00:00",
            "category": "not_a_real_category", "category_confidence": 0.9,
        }
    ]
    path = _write_jsonl(tmp_path, rows)

    with pytest.raises(ValueError):
        load_stale_records(path)


def _fake_scored_record(uid, conflict_type, cc_score, recency=1.0, similarity=0.5, always_llm=0.6):
    return {
        "uid": uid,
        "conflict_type": conflict_type,
        "category": "location",
        "category_confidence": 0.9,
        "contextclock_final_score": cc_score,
        "contextclock_level": "stale",
        "contextclock_time_decay": 0.5,
        "contextclock_contradiction": 0.5,
        "recency_only_score": recency,
        "similarity_only_score": similarity,
        "always_llm_score": always_llm,
        "always_llm_api_calls": 1,
    }


def test_aggregate_metrics_splits_by_conflict_type():
    scored = [
        _fake_scored_record("u1", "T1", 0.9),
        _fake_scored_record("u2", "T1", 0.8),
        _fake_scored_record("u3", "T2", 0.4),
        _fake_scored_record("u4", "T2", 0.3),
    ]

    result = aggregate_metrics(scored)

    assert result["n_total"] == 4
    assert result["n_t1"] == 2
    assert result["n_t2"] == 2
    assert result["overall"]["contextclock"]["distribution"]["n"] == 4
    assert result["t1"]["contextclock"]["distribution"]["n"] == 2
    assert result["t2"]["contextclock"]["distribution"]["n"] == 2


def test_aggregate_metrics_reflects_t1_vs_t2_difficulty_in_distributions():
    """
    Sanity check that the aggregation actually separates the slices
    correctly (not that T1 > T2 is guaranteed by real data -- that's
    an empirical question for the real run, not something to assert
    here). This just confirms the plumbing keeps scores in their
    correct bucket.
    """
    scored = [
        _fake_scored_record("u1", "T1", 0.9),
        _fake_scored_record("u2", "T2", 0.2),
    ]

    result = aggregate_metrics(scored)

    assert result["t1"]["contextclock"]["distribution"]["mean"] == 0.9
    assert result["t2"]["contextclock"]["distribution"]["mean"] == 0.2


def test_aggregate_metrics_raises_on_empty_input():
    with pytest.raises(ValueError):
        aggregate_metrics([])


def test_aggregate_metrics_includes_all_four_scoring_methods():
    scored = [_fake_scored_record("u1", "T1", 0.7)]

    result = aggregate_metrics(scored)

    assert set(result["overall"].keys()) == {
        "contextclock", "recency_only", "similarity_only", "always_llm"
    }