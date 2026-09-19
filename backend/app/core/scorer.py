from app.models.memory import Memory, StalenessScore, StalenessLevel
from app.core.decay import compute_time_decay, get_decay_explanation
from app.core.access_anomaly import compute_access_anomaly, get_anomaly_explanation
from app.core.retrieval import find_candidate_memories
from app.core.contradiction import detect_contradiction, MemoryRelationship


# Weights for the three signals — must sum to 1.0
# Time decay is the strongest signal since it's always available.
# Contradiction is powerful but requires an API call (Phase 2).
# Access anomaly is a soft supporting signal.
WEIGHTS = {
    "time_decay":     0.50,
    "contradiction":  0.30,
    "access_anomaly": 0.20,
}


def resolve_contradiction_score(
    memory: Memory,
    existing_memories: list[Memory],
) -> tuple[float, str]:
    """
    Phase 2 orchestration: retrieval (Step 3) + Gemini contradiction
    detection (Steps 5-6), combined into a single contradiction
    score usable by score_memory().

    Only memories created AFTER `memory` are considered as potential
    contradictors/superseders -- something can't be contradicted by
    a memory that already existed before it.

    Both CONTRADICTS and SUPERSEDES relationships count toward the
    score: a superseded memory is just as "no longer current" as a
    contradicted one, even though the two are logged separately in
    `reasoning` for qualitative analysis later (see Phase 2 schema
    design). If multiple newer candidates trigger a signal, the
    strongest one wins (max, not average) -- one clear contradiction
    shouldn't be diluted by weaker/unrelated comparisons.

    Returns (score, reasoning) so the caller can log/display why a
    particular score was assigned.
    """
    candidates = find_candidate_memories(memory, existing_memories)
    newer_candidates = [c for c in candidates if c.memory.created_at >= memory.created_at]

    if not newer_candidates:
        return 0.0, "No newer related memories found during retrieval."

    best_score = 0.0
    best_reasoning = "No contradiction or supersession detected among candidates."

    for candidate in newer_candidates:
        result = detect_contradiction(old_memory=memory, new_memory=candidate.memory)

        if result.relationship in (MemoryRelationship.CONTRADICTS, MemoryRelationship.SUPERSEDES):
            if result.score > best_score:
                best_score = result.score
                best_reasoning = (
                    f"[{result.relationship.value}] vs memory {candidate.memory.id!r} "
                    f"({candidate.memory.content!r}): {result.reasoning}"
                )

    return best_score, best_reasoning


def score_memory_full(
    memory: Memory,
    existing_memories: list[Memory],
) -> StalenessScore:
    """
    Full Phase 2 pipeline: computes the real contradiction score via
    retrieval + Gemini, then delegates to score_memory() for the
    actual weighted combination. This is now the "real" entry point
    for scoring a memory once Phase 2 is wired in; score_memory()
    itself is kept unchanged so its existing unit tests remain valid
    and so contradiction_score can still be injected manually/mocked
    in tests without touching the network.
    """
    contradiction_score, contradiction_reasoning = resolve_contradiction_score(
        memory, existing_memories
    )

    score = score_memory(memory, contradiction_score=contradiction_score)
    score.explanation += f" | Contradiction detail: {contradiction_reasoning}"
    return score


def compute_staleness_level(score: float) -> StalenessLevel:
    """
    Maps a final score (0.0 to 1.0) to a human-readable staleness level.

        0.0 - 0.30 → FRESH
        0.30 - 0.60 → AGING
        0.60 - 0.80 → STALE
        0.80 - 1.00 → EXPIRED
    """
    if score < 0.30:
        return StalenessLevel.FRESH
    elif score < 0.60:
        return StalenessLevel.AGING
    elif score < 0.80:
        return StalenessLevel.STALE
    else:
        return StalenessLevel.EXPIRED


def score_memory(
    memory: Memory,
    contradiction_score: float = 0.0,  # Phase 2 will pass real values here
) -> StalenessScore:
    """
    Computes the full staleness score for a memory.

    Args:
        memory: The Memory object to score.
        contradiction_score: A pre-computed contradiction score from Gemini Flash.
                             Defaults to 0.0 until Phase 2 wires it in.

    Returns:
        A fully populated StalenessScore object.
    """

    # --- Signal 1: Time Decay ---
    time_decay = compute_time_decay(memory.category, memory.created_at)

    # --- Signal 2: Contradiction (placeholder until Phase 2) ---
    # Will be replaced by Gemini Flash semantic contradiction detection
    contradiction = max(0.0, min(1.0, contradiction_score))

    # --- Signal 3: Access Anomaly ---
    access_anomaly = compute_access_anomaly(
        access_count=memory.access_count,
        created_at=memory.created_at,
        last_accessed_at=memory.last_accessed_at,
    )

    # --- Combine with weighted average ---
    final_score = round(
        WEIGHTS["time_decay"]     * time_decay +
        WEIGHTS["contradiction"]  * contradiction +
        WEIGHTS["access_anomaly"] * access_anomaly,
        4
    )

    # Clamp just in case of floating point edge cases
    final_score = min(max(final_score, 0.0), 1.0)

    # --- Determine level ---
    level = compute_staleness_level(final_score)

    # --- Build explanation ---
    decay_explanation = get_decay_explanation(
        memory.category, memory.created_at, time_decay
    )
    anomaly_explanation = get_anomaly_explanation(
        memory.access_count, memory.created_at, memory.last_accessed_at, access_anomaly
    )

    if contradiction > 0.0:
        contradiction_explanation = f"Contradiction signal: {contradiction:.2f} (detected by AI)."
    else:
        contradiction_explanation = "Contradiction signal: 0.00 (not yet checked)."

    explanation = (
        f"{decay_explanation} | "
        f"{contradiction_explanation} | "
        f"{anomaly_explanation}"
    )

    return StalenessScore(
        memory_id=memory.id,
        time_decay_score=time_decay,
        contradiction_score=contradiction,
        access_anomaly_score=access_anomaly,
        final_score=final_score,
        staleness_level=level,
        explanation=explanation,
    )