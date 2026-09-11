"""
Evaluation-only staleness scoring for the STALE benchmark.

METHODOLOGY NOTE (see paper limitations section):

STALE provides no access-pattern data -- verified empirically against
build_stale_dataset.py, which extracts no access_count / last_accessed_at
equivalent from the raw dataset (only m_old, m_new, timestamps, category,
conflict type). The production 3-signal scorer (app/core/scorer.py,
WEIGHTS with access_anomaly=0.20) therefore cannot be applied as-is:
app/core/access_anomaly.py has no reference_time parameter (unlike
decay.py) and falls back to a value derived from datetime.now() when
access_count=0 and last_accessed_at=None -- i.e. a wall-clock-dependent,
non-reproducible value correlated with a record's historical age, not a
genuine "no signal available" value.

Decision (discussed and confirmed): exclude access_anomaly entirely from
the STALE evaluation rather than forcing it to 0.0 under the original
weights. Forcing it to 0.0 would cap the maximum attainable score at 0.80
(0.50 + 0.30), making the existing EXPIRED threshold (>=0.80) reachable
only when both remaining signals hit exactly 1.0 simultaneously -- an
unreasonably narrow test of a threshold designed for a 3-signal system.

Instead, time_decay and contradiction are reweighted to preserve their
original 50:30 ratio while summing to 1.0:

    time_decay:    0.50 / 0.80 = 0.625
    contradiction: 0.30 / 0.80 = 0.375

This is a disclosed, evaluation-only deviation from the production
3-signal architecture. It should be reported as testing a reduced
2-signal variant of ContextClock on this benchmark, not as validating
the full system -- access_anomaly's contribution remains untested by
STALE and is noted as a limitation / future-work item requiring a
benchmark with genuine access-log data.

SCOPE NOTE: this module also skips app/core/retrieval.py entirely.
Production scoring first retrieves candidate memories, then checks
contradiction among them; STALE already hands us the correct
(m_old, m_new) pair directly; construction of the pair here so we are
testing contradiction-detection quality in isolation, not conflating it
with retrieval/candidate-selection quality.

Production scorer.py and its WEIGHTS are untouched by this module.
"""

from datetime import datetime

from app.models.memory import Memory, MemoryCategory, StalenessScore
from app.core.decay import compute_time_decay
from app.core.contradiction import detect_contradiction, MemoryRelationship, MODEL_NAME
from app.core.scorer import compute_staleness_level

# Renormalized from production WEIGHTS (time_decay=0.50, contradiction=0.30)
# so the two remaining signals sum to 1.0 with access_anomaly excluded.
# The ratio between the two signals is preserved exactly: 0.50:0.30 == 0.625:0.375.
STALE_EVAL_WEIGHTS = {
    "time_decay": 0.625,
    "contradiction": 0.375,
}


def score_stale_pair(
    m_old: str,
    m_new: str,
    category: MemoryCategory,
    old_timestamp: datetime,
    new_timestamp: datetime,
    model: str = MODEL_NAME,
) -> StalenessScore:
    """
    Computes a reduced 2-signal (time_decay + contradiction) staleness
    score for a single STALE (m_old, m_new) evaluation pair.

    model: overrides which Gemini model detect_contradiction() calls.
    Defaults to production MODEL_NAME; the STALE evaluation runner
    should pass an evaluation-tier model (e.g. gemini-3.5-flash-lite)
    to avoid gemini-3.6-flash's 20/day free-tier cap over 400 pairs,
    matching the same pattern used for category_classifier.py.

    time_decay is evaluated as of new_timestamp (not real wall-clock
    time), matching decay.py's reference_time mechanism -- the old
    memory's staleness is judged at the moment it was superseded, not
    at the moment this evaluation script happens to run.

    access_anomaly is deliberately excluded -- see module docstring.
    """
    old_memory = Memory(
        id="stale_old",
        content=m_old,
        category=category,
        user_id="stale_eval",
        agent_id="stale_eval",
        created_at=old_timestamp,
    )
    new_memory = Memory(
        id="stale_new",
        content=m_new,
        category=category,
        user_id="stale_eval",
        agent_id="stale_eval",
        created_at=new_timestamp,
    )

    time_decay = compute_time_decay(category, old_timestamp, reference_time=new_timestamp)

    contradiction_result = detect_contradiction(old_memory, new_memory, model=model)
    if contradiction_result.relationship in (
        MemoryRelationship.CONTRADICTS,
        MemoryRelationship.SUPERSEDES,
    ):
        contradiction = contradiction_result.score
    else:
        contradiction = 0.0

    final_score = round(
        STALE_EVAL_WEIGHTS["time_decay"] * time_decay
        + STALE_EVAL_WEIGHTS["contradiction"] * contradiction,
        4,
    )
    final_score = min(max(final_score, 0.0), 1.0)

    level = compute_staleness_level(final_score)

    explanation = (
        f"[STALE eval, 2-signal] Time decay: {time_decay:.2f} (as of new_timestamp). "
        f"Contradiction: {contradiction:.2f} "
        f"[{contradiction_result.relationship.value}] -- {contradiction_result.reasoning} "
        f"Access anomaly excluded: STALE provides no access-pattern data "
        f"(see methodology/limitations)."
    )

    return StalenessScore(
        memory_id="stale_pair",
        time_decay_score=time_decay,
        contradiction_score=contradiction,
        access_anomaly_score=0.0,
        final_score=final_score,
        staleness_level=level,
        explanation=explanation,
    )