from datetime import datetime, timedelta, timezone
from app.core.decay import compute_time_decay, get_decay_explanation, HALF_LIFE_DAYS
from app.models.memory import MemoryCategory


def test_brand_new_memory_is_fresh():
    """A memory created right now should have a score very close to 0."""
    score = compute_time_decay(MemoryCategory.EMPLOYMENT, datetime.now(timezone.utc))
    assert score < 0.01, f"Expected near 0, got {score}"
    print(f"✓ Brand new memory score: {score}")


def test_at_half_life_score_is_near_half():
    """At exactly the half-life age, score should be ~0.5."""
    half_life = HALF_LIFE_DAYS[MemoryCategory.EMPLOYMENT]  # 180 days
    created_at = datetime.now(timezone.utc) - timedelta(days=half_life)
    score = compute_time_decay(MemoryCategory.EMPLOYMENT, created_at)
    assert 0.45 < score < 0.55, f"Expected ~0.5, got {score}"
    print(f"✓ At half-life ({half_life} days), employment score: {score}")


def test_employment_decays_faster_than_personal():
    """Employment memories should decay faster than personal ones."""
    age = timedelta(days=365)
    created_at = datetime.now(timezone.utc) - age

    employment_score = compute_time_decay(MemoryCategory.EMPLOYMENT, created_at)
    personal_score = compute_time_decay(MemoryCategory.PERSONAL, created_at)

    assert (
        employment_score > personal_score
    ), f"Employment ({employment_score}) should decay faster than personal ({personal_score})"
    print(
        f"✓ After 1 year — Employment: {employment_score}, Personal: {personal_score}"
    )


def test_very_old_memory_approaches_one():
    """A 20-year-old employment memory should be nearly fully stale."""
    created_at = datetime.now(timezone.utc) - timedelta(days=365 * 20)
    score = compute_time_decay(MemoryCategory.EMPLOYMENT, created_at)
    assert score > 0.99, f"Expected >0.99, got {score}"
    print(f"✓ 20-year-old memory score: {score}")


def test_score_never_exceeds_one():
    """Score must always be clamped to [0.0, 1.0]."""
    created_at = datetime.now(timezone.utc) - timedelta(days=365 * 100)
    for category in MemoryCategory:
        score = compute_time_decay(category, created_at)
        assert 0.0 <= score <= 1.0, f"Score out of range for {category}: {score}"
    print("✓ All categories clamped within [0.0, 1.0]")


def test_explanation_is_readable():
    """Explanation should be a non-empty string."""
    created_at = datetime.now(timezone.utc) - timedelta(days=90)
    score = compute_time_decay(MemoryCategory.LOCATION, created_at)
    explanation = get_decay_explanation(MemoryCategory.LOCATION, created_at, score)
    assert isinstance(explanation, str)
    assert len(explanation) > 10
    print(f"✓ Explanation: {explanation}")


def test_reference_time_override_ignores_real_now():
    """
    A memory created 2 years before a FIXED reference_time should score
    ~0.75 for LOCATION (365-day half-life), regardless of what the real
    current date is. This is the behavior evaluation code (e.g. STALE
    dataset scoring) depends on.
    """
    reference_time = datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    created_at = reference_time - timedelta(days=365 * 2)  # 2x half-life for LOCATION

    score = compute_time_decay(
        MemoryCategory.LOCATION, created_at, reference_time=reference_time
    )
    assert 0.70 < score < 0.80, f"Expected ~0.75 at 2x half-life, got {score}"
    print(f"✓ Fixed reference_time (2023-06-15) score at 2x half-life: {score}")


def test_reference_time_none_matches_default_behavior():
    """
    Explicitly passing reference_time=None must produce the exact same
    score as omitting it, confirming backward compatibility with all
    pre-existing callers.
    """
    created_at = datetime.now(timezone.utc) - timedelta(days=180)

    score_default = compute_time_decay(MemoryCategory.EMPLOYMENT, created_at)
    score_explicit_none = compute_time_decay(
        MemoryCategory.EMPLOYMENT, created_at, reference_time=None
    )
    assert score_default == score_explicit_none, (
        f"reference_time=None should match omitting the argument: "
        f"{score_default} vs {score_explicit_none}"
    )
    print(f"✓ reference_time=None matches default: {score_default}")


def test_explanation_matches_score_with_reference_time():
    """
    get_decay_explanation must accept the same reference_time used to
    compute the score, so the displayed age and the numeric score
    describe the same moment in time rather than silently disagreeing.
    """
    reference_time = datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    created_at = reference_time - timedelta(days=730)  # 2 years before reference

    score = compute_time_decay(
        MemoryCategory.LOCATION, created_at, reference_time=reference_time
    )
    explanation = get_decay_explanation(
        MemoryCategory.LOCATION, created_at, score, reference_time=reference_time
    )
    assert "years" in explanation, f"Expected age in years, got: {explanation}"
    assert isinstance(explanation, str) and len(explanation) > 10
    print(f"✓ Explanation with fixed reference_time: {explanation}")