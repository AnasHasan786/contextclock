"""
Evaluation metrics for staleness scores on positive-only benchmarks.

METHODOLOGY NOTE (see paper limitations section):

STALE contains only genuine positive conflict pairs (verified: 400/400
rows are constructed old/new pairs describing a real change -- there
are no negative/non-conflicting pairs in the benchmark). This means
metrics that require negatives -- precision, specificity, false
positive rate, AUROC/ROC in the usual sense -- cannot be computed here.

What CAN be computed and reported honestly:

1. Detection rate: the fraction of known-positive pairs whose final
   score crosses a given staleness threshold. This is a RECALL-style
   measure ("of the genuinely stale pairs, how many did we catch?"),
   not a full accuracy measure -- it says nothing about how the
   system would behave on a pair that is NOT actually stale, because
   STALE never gives us one to test against.

2. Score distributions (mean/median/stdev/min/max), overall and
   stratified by conflict_type (T1=explicit, T2=implicit), which
   let the reader see HOW confidently pairs were flagged, not just
   whether they crossed a line, and directly support the T1-vs-T2
   difficulty comparison (Q4 in the research plan).

Any report generated from this module must retain the "recall on
positives only" framing -- do not present detection_rate as overall
accuracy.
"""

import statistics
from dataclasses import dataclass


@dataclass
class DistributionSummary:
    n: int
    mean: float
    median: float
    stdev: float
    minimum: float
    maximum: float


@dataclass
class DetectionRateResult:
    """
    threshold: the score cutoff a pair must meet or exceed to count
    as "detected." Typically one of the existing StalenessLevel
    boundaries (0.30=AGING, 0.60=STALE, 0.80=EXPIRED).
    detected: count of pairs with final_score >= threshold.
    total: total pairs evaluated.
    rate: detected / total.
    """
    threshold: float
    detected: int
    total: int
    rate: float


def summarize_distribution(scores: list[float]) -> DistributionSummary:
    """
    Computes descriptive statistics over a list of final_score values.
    Raises ValueError on an empty list rather than silently returning
    a degenerate summary -- an empty evaluation slice (e.g. a T1/T2
    split with zero rows) indicates a bug upstream and should be
    caught, not hidden behind zeros.
    """
    if not scores:
        raise ValueError("Cannot summarize an empty list of scores.")

    return DistributionSummary(
        n=len(scores),
        mean=round(statistics.mean(scores), 4),
        median=round(statistics.median(scores), 4),
        stdev=round(statistics.stdev(scores), 4) if len(scores) > 1 else 0.0,
        minimum=round(min(scores), 4),
        maximum=round(max(scores), 4),
    )


def detection_rate(scores: list[float], threshold: float) -> DetectionRateResult:
    """
    Fraction of `scores` that meet or exceed `threshold`.

    This is a recall-style measure over known-positive pairs only --
    see module docstring. It is NOT accuracy, and must not be
    reported as such.
    """
    if not scores:
        raise ValueError("Cannot compute detection rate over an empty list of scores.")

    detected = sum(1 for s in scores if s >= threshold)
    total = len(scores)
    return DetectionRateResult(
        threshold=threshold,
        detected=detected,
        total=total,
        rate=round(detected / total, 4),
    )


# The three existing StalenessLevel boundaries (scorer.py /
# compute_staleness_level), reused here as the standard set of
# thresholds reported for every evaluation slice.
STANDARD_THRESHOLDS = {
    "AGING": 0.30,
    "STALE": 0.60,
    "EXPIRED": 0.80,
}


def detection_rates_at_standard_thresholds(scores: list[float]) -> dict[str, DetectionRateResult]:
    """
    Convenience wrapper: computes detection_rate() at all three
    standard StalenessLevel boundaries in one call, so a report can
    show "% flagged as at least AGING / at least STALE / at least
    EXPIRED" side by side.
    """
    return {
        name: detection_rate(scores, threshold)
        for name, threshold in STANDARD_THRESHOLDS.items()
    }