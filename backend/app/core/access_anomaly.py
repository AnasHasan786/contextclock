from datetime import datetime, timezone, timedelta
from typing import Optional


def compute_access_anomaly(
    access_count: int,
    created_at: datetime,
    last_accessed_at: Optional[datetime],
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
    """

    now = datetime.now(timezone.utc)

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    memory_age_days = max(1.0, (now - created_at).total_seconds() / 86400)

    # --- Signal 1: Recency Gap ---
    # How long has it been since the memory was last accessed,
    # relative to how old the memory is?
    if last_accessed_at is None:
        # Never accessed — only suspicious if memory is old
        # A 2-day-old memory never accessed = fine
        # A 1-year-old memory never accessed = mildly suspicious
        recency_gap_score = min(memory_age_days / 365, 1.0) * 0.3
    else:
        if last_accessed_at.tzinfo is None:
            last_accessed_at = last_accessed_at.replace(tzinfo=timezone.utc)

        days_since_access = (now - last_accessed_at).total_seconds() / 86400

        # Gap ratio: silence duration vs total memory age
        gap_ratio = days_since_access / memory_age_days
        recency_gap_score = min(gap_ratio, 1.0)

    # --- Signal 2: Access Drought ---
    # If access_count is high, we expect regular access.
    # Sudden silence after heavy use = strong anomaly.
    if access_count == 0 or last_accessed_at is None:
        drought_score = 0.0
    else:
        if last_accessed_at.tzinfo is None:
            last_accessed_at = last_accessed_at.replace(tzinfo=timezone.utc)

        days_since_access = (now - last_accessed_at).total_seconds() / 86400

        # Expected access frequency: access_count spread over memory age
        expected_interval_days = memory_age_days / max(access_count, 1)

        # How many expected intervals have passed without access?
        missed_intervals = days_since_access / max(expected_interval_days, 0.1)

        # Cap at 1.0: beyond 5 missed intervals = maximum drought score
        drought_score = min(missed_intervals / 5.0, 1.0)

    # --- Combine ---
    # Drought signal weighted higher when access_count is meaningful (>= 3)
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
) -> str:
    """
    Returns a human-readable explanation of the access anomaly score.
    """
    now = datetime.now(timezone.utc)

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    memory_age_days = max(1.0, (now - created_at).total_seconds() / 86400)

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
        f"Memory is {int(memory_age_days)} days old. "
        f"Access anomaly score: {score:.2f}."
    )
