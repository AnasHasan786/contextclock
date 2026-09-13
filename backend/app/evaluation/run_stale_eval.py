"""
STALE evaluation runner (Phase 2 evaluation, Steps 10-15).

This is the script that actually produces the paper's quantitative
results. Given stale_eval.jsonl (400 records prepared by
build_stale_dataset.py), it:

1. Loads and parses every record.
2. Scores each (m_old, m_new) pair with ContextClock's reduced
   2-signal evaluation scorer (stale_scorer.score_stale_pair --
   access_anomaly excluded, see that module's docstring for why).
3. Scores each pair against the three literature-grounded baselines
   in app/core/baselines.py (recency-only, similarity-only,
   always-LLM), for the Q5 comparison.
4. Aggregates results into overall / T1 / T2 metrics using
   app/evaluation/metrics.py (detection rate at standard thresholds +
   score distributions -- see that module for why these are the only
   metrics STALE's all-positive-pairs design can support).

USAGE (run locally, NOT in an automated/sandboxed context -- this
makes up to ~800 real Gemini calls: ~400 for ContextClock's
contradiction detection + ~400 for the always-LLM baseline):

    python -m app.evaluation.run_stale_eval \\
        --input path/to/stale_eval.jsonl \\
        --output path/to/stale_eval_results.json \\
        --model gemini-3.5-flash-lite \\
        [--limit 20]   # optional: smoke-test on a subset first

KNOWN RESULT TO EXPECT (methodology note, not a bug): recency_only_score
will score 1.0 on ~100% of rows, because STALE's construction
guarantees a newer same-category memory always exists. This is the
exact triviality problem discussed when this runner was designed --
report it, but do not present it as recency-only being a strong
detector; see metrics.py's docstring for the full explanation.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from app.models.memory import MemoryCategory
from app.core.baselines import recency_only_score, similarity_only_score, always_llm_score
from app.evaluation.stale_scorer import score_stale_pair, build_stale_memory_pair
from app.evaluation.metrics import summarize_distribution, detection_rates_at_standard_thresholds


def load_stale_records(path: str) -> list[dict]:
    """
    Loads stale_eval.jsonl and parses the fields the scorers need
    (category -> MemoryCategory, timestamps -> datetime). Other
    fields (uid, explanation, category_confidence, etc.) pass through
    unchanged for provenance in the results file.

    Raises on any row with an unparseable category or timestamp
    rather than silently skipping it -- a malformed row this late in
    the pipeline indicates a bug upstream (build_stale_dataset.py)
    that should be investigated, not masked.
    """
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                row["category"] = MemoryCategory(row["category"])
                row["old_timestamp"] = datetime.fromisoformat(row["old_timestamp"])
                row["new_timestamp"] = datetime.fromisoformat(row["new_timestamp"])
            except Exception as e:
                raise ValueError(f"Failed to parse stale_eval.jsonl line {line_num}: {e}") from e
            records.append(row)
    return records


def score_records(records: list[dict], model: str, verbose: bool = True) -> list[dict]:
    """
    Scores every record against ContextClock's reduced 2-signal
    evaluation scorer and the three baselines. Makes real Gemini API
    calls (via score_stale_pair and always_llm_score) -- this is the
    expensive, network-dependent step; everything downstream
    (aggregate_metrics) is pure and offline.
    """
    scored = []
    total = len(records)

    for i, row in enumerate(records, start=1):
        cc_result = score_stale_pair(
            m_old=row["m_old"],
            m_new=row["m_new"],
            category=row["category"],
            old_timestamp=row["old_timestamp"],
            new_timestamp=row["new_timestamp"],
            model=model,
        )

        old_memory, new_memory = build_stale_memory_pair(
            row["m_old"], row["m_new"], row["category"], row["old_timestamp"], row["new_timestamp"]
        )
        existing = [old_memory, new_memory]

        recency_score, recency_reasoning = recency_only_score(old_memory, existing)
        similarity_score, similarity_reasoning = similarity_only_score(old_memory, existing)
        always_llm_result, always_llm_reasoning, always_llm_calls = always_llm_score(
            old_memory, existing, model=model
        )

        scored.append({
            "uid": row["uid"],
            "conflict_type": row["conflict_type"],
            "category": row["category"].value,
            "category_confidence": row["category_confidence"],
            "contextclock_final_score": cc_result.final_score,
            "contextclock_level": cc_result.staleness_level.value,
            "contextclock_time_decay": cc_result.time_decay_score,
            "contextclock_contradiction": cc_result.contradiction_score,
            "recency_only_score": recency_score,
            "similarity_only_score": similarity_score,
            "always_llm_score": always_llm_result,
            "always_llm_api_calls": always_llm_calls,
        })

        if verbose and (i % 25 == 0 or i == total):
            print(f"  [{i}/{total}] scored uid={row['uid']}")

    return scored


def _metrics_for_scores(scores: list[float]) -> dict:
    return {
        "distribution": summarize_distribution(scores).__dict__,
        "detection_rates": {
            name: result.__dict__
            for name, result in detection_rates_at_standard_thresholds(scores).items()
        },
    }


def aggregate_metrics(scored_records: list[dict]) -> dict:
    """
    Pure aggregation step -- no network calls, fully unit-testable.
    Computes overall / T1 / T2 metrics for ContextClock's final_score
    and, for reference, each baseline's score.
    """
    if not scored_records:
        raise ValueError("Cannot aggregate metrics over zero scored records.")

    t1 = [r for r in scored_records if r["conflict_type"] == "T1"]
    t2 = [r for r in scored_records if r["conflict_type"] == "T2"]

    def slice_metrics(subset: list[dict], score_key: str) -> dict:
        return _metrics_for_scores([r[score_key] for r in subset])

    results = {"n_total": len(scored_records), "n_t1": len(t1), "n_t2": len(t2)}

    for label, subset in (("overall", scored_records), ("t1", t1), ("t2", t2)):
        if not subset:
            continue
        results[label] = {
            "contextclock": slice_metrics(subset, "contextclock_final_score"),
            "recency_only": slice_metrics(subset, "recency_only_score"),
            "similarity_only": slice_metrics(subset, "similarity_only_score"),
            "always_llm": slice_metrics(subset, "always_llm_score"),
        }

    return results


def main():
    parser = argparse.ArgumentParser(description="Run the STALE benchmark evaluation.")
    parser.add_argument("--input", required=True, help="Path to stale_eval.jsonl")
    parser.add_argument("--output", required=True, help="Path to write results JSON")
    parser.add_argument(
        "--model", default="gemini-3.5-flash-lite",
        help="Gemini model for contradiction detection (default: eval-tier model, avoids the 20/day cap on gemini-3.6-flash)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Optional: only score the first N records (for smoke-testing before a full 400-row run)",
    )
    args = parser.parse_args()

    records = load_stale_records(args.input)
    if args.limit is not None:
        records = records[: args.limit]

    print(f"Loaded {len(records)} records. Scoring with model={args.model}...")
    scored = score_records(records, model=args.model)

    print("Aggregating metrics...")
    metrics = aggregate_metrics(scored)

    output = {"metrics": metrics, "per_record_results": scored}
    Path(args.output).write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote results to {args.output}")


if __name__ == "__main__":
    main()