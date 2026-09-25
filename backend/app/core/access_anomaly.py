from datetime import datetime, timezone, timedelta
from typing import Optional


def compute_access_anomaly(
    access_count: int,
    created_at: datetime,
    last_accessed_at: Optional[datetime],
    reference_time: datetime | None = None,
) -> float:
    """
    Computes an access anomaly score between 0.0 and 1.0.

    Logic:
    - If a memory has never been accessed → low anomaly (agent just hasn't used it yet)
    - If a memory was accessed regularly but hasn't been accessed in a long time → high anomaly
    - If a memory was just created and never accessed → near 0 (normal, not suspicious)

    Score interpretation:
        0.0 = no anomaly, access pattern is normal
        1.0 = strong anomaly, agent appears to be avoiding this memory

    Two sub-signals combined:
        1. Recency gap: how long since last access relative to memory age
        2. Access drought: access_count is high but recent access is absent

    reference_time: the point in time this is measured "as of." Defaults
    to the real current time (production use). Evaluation code may pass
    a fixed historical timestamp for reproducible offline scoring --
    mirrors the same parameter already on compute_time_decay().
    """

    now = reference_time if reference_time is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    memory_age_days = max(1.0, (now - created_at).total_seconds() / 86400)

    # --- Signal 1: Recency Gap ---
    if last_accessed_at is None:
        recency_gap_score = min(memory_age_days / 365, 1.0) * 0.3
    else:
        if last_accessed_at.tzinfo is None:
            last_accessed_at = last_accessed_at.replace(tzinfo=timezone.utc)

        days_since_access = (now - last_accessed_at).total_seconds() / 86400
        gap_ratio = days_since_access / memory_age_days
        recency_gap_score = min(gap_ratio, 1.0)

    # --- Signal 2: Access Drought ---
    if access_count == 0 or last_accessed_at is None:
        drought_score = 0.0
    else:
        if last_accessed_at.tzinfo is None:
            last_accessed_at = last_accessed_at.replace(tzinfo=timezone.utc)

        days_since_access = (now - last_accessed_at).total_seconds() / 86400
        expected_interval_days = memory_age_days / max(access_count, 1)
        missed_intervals = days_since_access / max(expected_interval_days, 0.1)
        drought_score = min(missed_intervals / 5.0, 1.0)

    # --- Combine ---
    if access_count >= 3:
        final_score = (0.35 * recency_gap_score) + (0.65 * drought_score)
    else:
        final_score = (0.70 * recency_gap_score) + (0.30 * drought_score)

    return round(min(max(final_score, 0.0), 1.0), 4)


def get_anomaly_explanation(
    access_count: int,
    created_at: datetime,
    last_accessed_at: Optional[datetime],
    score: float,
    reference_time: datetime | None = None,
) -> str:
    """
    Returns a human-readable explanation of the access anomaly score.

    reference_time: must match whatever was passed to
    compute_access_anomaly() to produce `score`, so the displayed age
    and the numeric score describe the same moment in time rather than
    silently disagreeing. Defaults to real current time (production use).
    """
    now = reference_time if reference_time is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    # Unfloored — for display only. compute_access_anomaly() keeps its own
    # floor for the score math; this one is purely cosmetic.
    real_age_days = (now - created_at).total_seconds() / 86400

    if real_age_days < 1 / 24:
        age_str = "less than an hour old"
    elif real_age_days < 1:
        age_str = f"{int(real_age_days * 24)} hours old"
    else:
        age_str = f"{int(real_age_days)} days old"

    if last_accessed_at is None:
        access_str = "never accessed"
    else:
        if last_accessed_at.tzinfo is None:
            last_accessed_at = last_accessed_at.replace(tzinfo=timezone.utc)
        days_since = (now - last_accessed_at).total_seconds() / 86400
        if days_since < 1:
            access_str = "last accessed today"
        elif days_since < 30:
            access_str = f"last accessed {int(days_since)} days ago"
        else:
            access_str = f"last accessed {int(days_since / 30)} months ago"

    return (
        f"Memory accessed {access_count} time(s), {access_str}. "
        f"Memory is {age_str}. "
        f"Access anomaly score: {score:.2f}."
    )
