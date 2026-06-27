from datetime import datetime, timedelta, timezone
from app.models.memory import Memory, MemoryCategory, StalenessLevel
from app.core.scorer import score_memory, WEIGHTS


def make_memory(
    category=MemoryCategory.EMPLOYMENT,
    age_days=0,
    access_count=0,
    last_accessed_days_ago=None,
) -> Memory:
    """Helper to build Memory objects for tests."""
    created_at = datetime.now(timezone.utc) - timedelta(days=age_days)
    last_accessed_at = (
        datetime.now(timezone.utc) - timedelta(days=last_accessed_days_ago)
        if last_accessed_days_ago is not None
        else None
    )
    return Memory(
        id="mem_test",
        content="User works at Google",
        category=category,
        user_id="user_001",
        agent_id="agent_001",
        created_at=created_at,
        access_count=access_count,
        last_accessed_at=last_accessed_at,
    )


def test_brand_new_memory_is_fresh():
    """A just-created memory with no history should be FRESH."""
    memory = make_memory(age_days=0)
    result = score_memory(memory)
    assert result.staleness_level == StalenessLevel.FRESH
    assert result.final_score < 0.30
    print(f"✓ Brand new memory → FRESH (score: {result.final_score})")


def test_very_old_memory_is_stale_or_expired():
    """
    A 10-year-old employment memory that was heavily used
    and then abandoned should be at least STALE.
    Without a contradiction signal, STALE is the correct ceiling —
    EXPIRED requires all three signals firing together.
    """
    memory = make_memory(
        category=MemoryCategory.EMPLOYMENT,
        age_days=3650,
        access_count=50,
        last_accessed_days_ago=3000
    )
    result = score_memory(memory)
    assert result.staleness_level in (StalenessLevel.STALE, StalenessLevel.EXPIRED), (
        f"Expected STALE or EXPIRED, got {result.staleness_level} (score: {result.final_score})"
    )
    assert result.final_score >= 0.60
    print(f"✓ 10-year-old abandoned memory → {result.staleness_level.value} (score: {result.final_score})")


def test_contradiction_raises_score():
    """Adding a contradiction score should increase final score."""
    memory = make_memory(age_days=30)
    without_contradiction = score_memory(memory, contradiction_score=0.0)
    with_contradiction = score_memory(memory, contradiction_score=0.9)
    assert with_contradiction.final_score > without_contradiction.final_score
    print(
        f"✓ Contradiction raises score: "
        f"{without_contradiction.final_score} → {with_contradiction.final_score}"
    )


def test_weights_sum_to_one():
    """Weights must always sum to exactly 1.0."""
    total = sum(WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"
    print(f"✓ Weights sum to {total}")


def test_score_has_all_fields():
    """StalenessScore must have all fields populated."""
    memory = make_memory(age_days=90, access_count=5, last_accessed_days_ago=60)
    result = score_memory(memory)
    assert result.memory_id == "mem_test"
    assert 0.0 <= result.time_decay_score <= 1.0
    assert 0.0 <= result.contradiction_score <= 1.0
    assert 0.0 <= result.access_anomaly_score <= 1.0
    assert 0.0 <= result.final_score <= 1.0
    assert isinstance(result.explanation, str) and len(result.explanation) > 0
    print(f"✓ All fields populated. Final score: {result.final_score}")


def test_personal_category_ages_slower_than_employment():
    """At 1 year old, personal memory should be fresher than employment."""
    employment = make_memory(category=MemoryCategory.EMPLOYMENT, age_days=365)
    personal = make_memory(category=MemoryCategory.PERSONAL, age_days=365)
    emp_score = score_memory(employment)
    per_score = score_memory(personal)
    assert emp_score.final_score > per_score.final_score
    print(
        f"✓ After 1 year — Employment: {emp_score.final_score}, "
        f"Personal: {per_score.final_score}"
    )


def test_explanation_contains_all_three_signals():
    """Explanation string should mention all three signal results."""
    memory = make_memory(age_days=200, access_count=10, last_accessed_days_ago=100)
    result = score_memory(memory, contradiction_score=0.4)
    assert "decay" in result.explanation.lower()
    assert "contradiction" in result.explanation.lower()
    assert (
        "anomaly" in result.explanation.lower()
        or "accessed" in result.explanation.lower()
    )
    print(f"✓ Explanation covers all signals")
