from datetime import datetime, timedelta, timezone
from app.core.access_anomaly import compute_access_anomaly, get_anomaly_explanation


def test_brand_new_never_accessed_is_low():
    """New memory never accessed = not suspicious at all."""
    created_at = datetime.now(timezone.utc) - timedelta(days=1)
    score = compute_access_anomaly(
        access_count=0, created_at=created_at, last_accessed_at=None
    )
    assert score < 0.15, f"Expected low score, got {score}"
    print(f"✓ Brand new, never accessed: {score}")


def test_old_memory_never_accessed_is_mildly_suspicious():
    """A 2-year-old memory never accessed = mildly suspicious."""
    created_at = datetime.now(timezone.utc) - timedelta(days=730)
    score = compute_access_anomaly(
        access_count=0, created_at=created_at, last_accessed_at=None
    )
    assert score > 0.1, f"Expected some suspicion, got {score}"
    print(f"✓ 2-year-old, never accessed: {score}")


def test_recently_accessed_is_low():
    """Memory accessed yesterday = no anomaly."""
    created_at = datetime.now(timezone.utc) - timedelta(days=60)
    last_accessed = datetime.now(timezone.utc) - timedelta(days=1)
    score = compute_access_anomaly(
        access_count=10, created_at=created_at, last_accessed_at=last_accessed
    )
    assert score < 0.2, f"Expected low score, got {score}"
    print(f"✓ Accessed yesterday (10 times total): {score}")


def test_heavily_used_then_abandoned_is_high():
    """Memory accessed 20 times but silent for 6 months = high anomaly."""
    created_at = datetime.now(timezone.utc) - timedelta(days=365)
    last_accessed = datetime.now(timezone.utc) - timedelta(days=180)
    score = compute_access_anomaly(
        access_count=20, created_at=created_at, last_accessed_at=last_accessed
    )
    assert score > 0.5, f"Expected high anomaly, got {score}"
    print(f"✓ Heavily used then abandoned for 6 months: {score}")


def test_score_always_in_range():
    """Score must always be between 0.0 and 1.0."""
    cases = [
        (0, timedelta(days=1), None),
        (100, timedelta(days=500), timedelta(days=400)),
        (1, timedelta(days=30), timedelta(days=29)),
        (50, timedelta(days=1000), timedelta(days=999)),
    ]
    for access_count, age, last_access_ago in cases:
        created_at = datetime.now(timezone.utc) - age
        last_accessed = (
            datetime.now(timezone.utc) - last_access_ago if last_access_ago else None
        )
        score = compute_access_anomaly(access_count, created_at, last_accessed)
        assert 0.0 <= score <= 1.0, f"Out of range: {score}"
    print("✓ All scores within [0.0, 1.0]")


def test_explanation_is_readable():
    """Explanation should be a meaningful string."""
    created_at = datetime.now(timezone.utc) - timedelta(days=90)
    last_accessed = datetime.now(timezone.utc) - timedelta(days=45)
    score = compute_access_anomaly(5, created_at, last_accessed)
    explanation = get_anomaly_explanation(5, created_at, last_accessed, score)
    assert isinstance(explanation, str) and len(explanation) > 10
    print(f"✓ Explanation: {explanation}")


def test_reference_time_override_ignores_real_now():
    """
    A memory accessed a long time before a FIXED reference_time should
    show a high recency gap regardless of what the real current date
    is -- the behavior evaluation code (e.g. STALE dataset scoring)
    would depend on if it ever needs this signal computed historically.
    """
    reference_time = datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    created_at = reference_time - timedelta(days=200)
    last_accessed_at = reference_time - timedelta(days=190)  # long silence since

    score = compute_access_anomaly(
        access_count=1,
        created_at=created_at,
        last_accessed_at=last_accessed_at,
        reference_time=reference_time,
    )
    assert score > 0.5, f"Expected a high anomaly score for a long-silent memory, got {score}"
    print(f"✓ Fixed reference_time (2023-06-15) score for long-silent memory: {score}")


def test_reference_time_none_matches_default_behavior():
    """
    Explicitly passing reference_time=None must produce the exact same
    score as omitting it, confirming backward compatibility with all
    pre-existing callers.
    """
    created_at = datetime.now(timezone.utc) - timedelta(days=180)
    last_accessed_at = datetime.now(timezone.utc) - timedelta(days=30)

    score_default = compute_access_anomaly(
        access_count=2, created_at=created_at, last_accessed_at=last_accessed_at
    )
    score_explicit_none = compute_access_anomaly(
        access_count=2, created_at=created_at, last_accessed_at=last_accessed_at,
        reference_time=None,
    )
    assert score_default == score_explicit_none, (
        f"reference_time=None should match omitting the argument: "
        f"{score_default} vs {score_explicit_none}"
    )
    print(f"✓ reference_time=None matches default: {score_default}")


def test_explanation_matches_score_with_reference_time():
    """
    get_anomaly_explanation must accept the same reference_time used to
    compute the score, so the displayed age/last-accessed text and the
    numeric score describe the same moment in time rather than
    silently disagreeing.
    """
    reference_time = datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    created_at = reference_time - timedelta(days=400)
    last_accessed_at = reference_time - timedelta(days=40)

    score = compute_access_anomaly(
        access_count=1, created_at=created_at, last_accessed_at=last_accessed_at,
        reference_time=reference_time,
    )
    explanation = get_anomaly_explanation(
        access_count=1, created_at=created_at, last_accessed_at=last_accessed_at,
        score=score, reference_time=reference_time,
    )
    assert "days ago" in explanation or "months ago" in explanation
    assert isinstance(explanation, str) and len(explanation) > 10
    print(f"✓ Explanation with fixed reference_time: {explanation}")