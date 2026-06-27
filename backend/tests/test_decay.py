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
