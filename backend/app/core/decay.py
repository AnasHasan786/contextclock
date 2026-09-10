import math
from datetime import datetime, timezone
from app.models.memory import MemoryCategory

# Half-life in days for each category.
# Half-life = number of days after which a memory is considered 50% stale.
# After 2x half-life it's ~75% stale. After 3x it's ~87% stale.

HALF_LIFE_DAYS: dict[MemoryCategory, float] = {
    MemoryCategory.EMPLOYMENT: 180,  # jobs change ~every 6 months on average
    MemoryCategory.LOCATION: 365,  # people move ~once a year
    MemoryCategory.RELATIONSHIP: 540,  # relationships change slower
    MemoryCategory.PREFERENCE: 730,  # preferences shift over ~2 years
    MemoryCategory.PERSONAL: 3650,  # name/birthday almost never changes
    MemoryCategory.FACT: 730,  # general facts decay slowly
}


def compute_time_decay(
    category: MemoryCategory,
    created_at: datetime,
    reference_time: datetime | None = None,
) -> float:
    """
    ...
    reference_time: the point in time decay is measured "as of."
    Defaults to the real current time (production use). Evaluation
    code may pass a fixed historical timestamp to simulate staleness
    as of a specific past moment (e.g. STALE dataset evaluation).
    """
    half_life = HALF_LIFE_DAYS[category]
    decay_constant = math.log(2) / half_life

    now = reference_time if reference_time is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    age_in_days = (now - created_at).total_seconds() / 86400
    age_in_days = max(0.0, age_in_days)

    score = 1 - math.exp(-decay_constant * age_in_days)
    return round(min(max(score, 0.0), 1.0), 4)


def get_decay_explanation(
    category: MemoryCategory,
    created_at: datetime,
    score: float,
    reference_time: datetime | None = None,
) -> str:
    """
    Returns a human-readable explanation of the decay score.
    Used in the dashboard and API responses.

    reference_time: must match whatever was passed to compute_time_decay()
    to produce `score`, so the displayed age and the score stay consistent.
    Defaults to real current time (production use).
    """
    half_life = HALF_LIFE_DAYS[category]

    now = reference_time if reference_time is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    age_in_days = max(0.0, (now - created_at).total_seconds() / 86400)

    if age_in_days < 1:
        age_str = f"{int(age_in_days * 24)} hours"
    elif age_in_days < 30:
        age_str = f"{int(age_in_days)} days"
    elif age_in_days < 365:
        age_str = f"{int(age_in_days / 30)} months"
    else:
        age_str = f"{round(age_in_days / 365, 1)} years"

    return (
        f"Memory is {age_str} old. "
        f"Category '{category.value}' has a half-life of {half_life} days. "
        f"Time decay score: {score:.2f}."
    )
