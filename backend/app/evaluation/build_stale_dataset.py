"""
STALE dataset adapter for ContextClock evaluation.

Converts the STALEproj/STALE benchmark (400 validated M_old/M_new
conflict pairs) into a flat, ContextClock-friendly JSONL format.

Design decisions (see project notes for full justification):
- relevant_session_index is always length 2 across all 400 rows
  (verified empirically) -> index [0] = old session, [1] = new session,
  no branching logic needed.
- probing_queries and haystack_session are intentionally excluded.
  They belong to STALE's own long-context evaluation protocol, which
  ContextClock is not replicating; we only borrow the validated
  conflict pairs themselves.
- `type` (T1/T2 = explicit/implicit conflict, per STALE's own
  convention) is preserved as `conflict_type` so evaluation results
  can later be stratified by explicit vs. implicit difficulty -- this
  connects directly to the literature finding that LLM judges perform
  worse on implicit conflicts.
- MemoryCategory is assigned via classify_memory_category()
  (app/core/category_classifier.py), NOT by parsing the explanation
  field. Only ~12% of explanations carry an extractable ontology-style
  tag (verified empirically, and not concentrated in either conflict
  type), so string-parsing was not viable as a primary mapping
  strategy. m_old and m_new are classified JOINTLY (one shared
  category per pair, one Gemini call per row) since they describe the
  same underlying fact by construction. Where an ontology tag IS
  present in the explanation, it is preserved in `raw_ontology_tag`
  purely as a non-authoritative cross-check, never as ground truth.
  category_confidence and category_reasoning are kept alongside the
  category itself so low-confidence classifications can be identified
  and spot-checked or excluded during evaluation, rather than treated
  as silently equally reliable.

  NOTE: this makes one real Gemini API call per row (400 total) each
  time the script runs, using EVALUATION_MODEL (gemini-3.5-flash-lite)
  rather than the production default (gemini-3.6-flash). This choice
  went through two wrong guesses first -- gemini-3.6-flash's real
  limit turned out to be 20 requests/DAY (not per-minute, as first
  assumed), and gemini-2.0-flash-lite turned out to be deprecated
  (404). The final choice was verified directly against the account's
  live rate-limit dashboard rather than public docs/search results,
  which were stale or inconsistent for these newer model generations.
  This is a disclosed evaluation-only deviation, not a silent one --
  the contradiction-detection evaluation pass (not yet built) will
  need the same treatment, since contradiction.py also defaults to
  gemini-3.6-flash.
- All 400 STALE rows are positive (genuine contradiction) pairs --
  verified by manual inspection of flagged rows. STALE contains no
  negative / non-conflicting examples. This script does not invent
  any; the absence of negatives is a documented evaluation limitation,
  to be addressed separately with ContextClock's own synthetic
  UNRELATED/CONSISTENT test cases.
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from datasets import load_dataset

from app.core.category_classifier import classify_memory_category

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# gemini-3.6-flash's free tier caps at only 20 requests/DAY (confirmed
# from a live 429 response, quotaId=
# GenerateRequestsPerDayPerProjectPerModel-FreeTier, quotaValue=20) --
# far too restrictive for a 400-row batch evaluation. gemini-2.0-flash-lite
# was tried next but returned 404 NOT_FOUND (deprecated; Google's own
# error response names gemini-3.5-flash-lite as the replacement).
# gemini-3.5-flash-lite is used here instead, verified directly against
# the account's live AI Studio rate-limit dashboard (not assumed from
# search results, after two prior wrong guesses): 15 RPM / 250K TPM /
# 500 RPD on the free tier -- comfortably covers a 400-row run.
# This is a disclosed deviation from the production default
# (gemini-3.6-flash, used in contradiction.py and as
# category_classifier.py's own default) -- document this in the
# paper's methodology/limitations section.
EVALUATION_MODEL = "gemini-3.5-flash-lite"

# 15 RPM confirmed for gemini-3.5-flash-lite; 5s/request (12 RPM)
# keeps a safety margin below that.
REQUEST_INTERVAL_SECONDS = 5

# Known prefixes used by category_classifier.py's fallback path (see
# _fallback_result). A record is considered a "fallback" -- i.e. not
# a genuine LLM classification, and a candidate for re-running -- if
# its confidence is exactly 0.0 AND its reasoning starts with one of
# these. This is a reliable detector because these are the only two
# code paths that ever produce confidence=0.0 in category_classifier.py.
_FALLBACK_REASONING_PREFIXES = ("API call failed", "Response did not parse to schema")

# Loose heuristic for an ontology-style tag anywhere in the explanation,
# e.g. "Spatiotemporal_Context.location(city)". Matches a capitalized
# dotted identifier, optionally followed by a parenthesized qualifier.
# This is a best-effort cross-check only -- see module docstring.
ONTOLOGY_TAG_PATTERN = re.compile(r"\b[A-Z][a-zA-Z]*_?[A-Za-z]*\.[a-z_]+(\([a-z]+\))?")

OUTPUT_PATH = Path(__file__).parent / "data" / "stale_eval.jsonl"


def _parse_timestamp(raw: str | datetime) -> datetime:
    """
    Normalize a STALE timestamp into a timezone-aware datetime (UTC).

    The `datasets` library returns this field as an actual datetime.datetime
    object (verified from a runtime TypeError), not the plain string it
    appeared to be in earlier debug output -- that appearance was an
    artifact of json.dumps(default=str) silently stringifying it for
    display. Both cases are handled here defensively.
    """
    if isinstance(raw, datetime):
        dt = raw
    else:
        dt = datetime.strptime(raw, TIMESTAMP_FORMAT)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _extract_ontology_tag(explanation: str) -> str | None:
    """
    Return the first ontology-style tag found anywhere in the explanation
    string, or None if absent. Non-authoritative -- see module docstring.
    """
    match = ONTOLOGY_TAG_PATTERN.search(explanation)
    return match.group(0) if match else None


def _is_fallback_record(record: dict) -> bool:
    """True if this record's category came from the safe-fallback path
    (API failure or unparseable response) rather than a genuine
    LLM classification, and should be re-attempted on a future run."""
    return record["category_confidence"] == 0.0 and record["category_reasoning"].startswith(
        _FALLBACK_REASONING_PREFIXES
    )


def _classify_with_retry(m_old: str, m_new: str, max_retries: int = 2, retry_wait_seconds: int = 60):
    """
    Calls classify_memory_category (using EVALUATION_MODEL, not the
    production default), retrying up to max_retries times (waiting
    retry_wait_seconds between attempts) if the result landed on the
    fallback path. Returns whatever the final attempt produces, even
    if it's still a fallback -- this is a best-effort safety net for
    transient rate-limit/server errors, not a guarantee of success.
    """
    result = classify_memory_category(content=m_old, related_content=m_new, model=EVALUATION_MODEL)
    attempt = 0
    while _is_fallback_record(
        {"category_confidence": result.confidence, "category_reasoning": result.reasoning}
    ) and attempt < max_retries:
        attempt += 1
        print(f"    retry {attempt}/{max_retries} after fallback, waiting {retry_wait_seconds}s...")
        time.sleep(retry_wait_seconds)
        result = classify_memory_category(content=m_old, related_content=m_new, model=EVALUATION_MODEL)
    return result


def build_record(row: dict, category_result=None) -> dict:
    """
    Convert a single raw STALE row into a ContextClock evaluation record.

    category_result: if provided, reuse this already-computed
    CategoryClassificationResult instead of calling the classifier
    again. Used by build_stale_dataset() to avoid re-classifying rows
    that already succeeded on a previous run.
    """
    old_idx, new_idx = row["relevant_session_index"]
    old_timestamp = _parse_timestamp(row["timestamps"][old_idx])
    new_timestamp = _parse_timestamp(row["timestamps"][new_idx])
    gap_days = (new_timestamp - old_timestamp).days

    if category_result is None:
        category_result = _classify_with_retry(m_old=row["M_old"], m_new=row["M_new"])

    return {
        "uid": row["uid"],
        "m_old": row["M_old"],
        "m_new": row["M_new"],
        "explanation": row["explanation"],
        "conflict_type": row["type"],  # "T1" (explicit) or "T2" (implicit)
        "old_timestamp": old_timestamp.isoformat(),
        "new_timestamp": new_timestamp.isoformat(),
        "gap_days": gap_days,
        "raw_ontology_tag": _extract_ontology_tag(row["explanation"]),
        "category": category_result.category.value,
        "category_confidence": category_result.confidence,
        "category_reasoning": category_result.reasoning,
    }


def build_stale_dataset(output_path: Path = OUTPUT_PATH) -> int:
    """
    Load STALE, convert all rows, write to JSONL.

    Self-healing / resumable: if output_path already contains records
    from a previous run, records that were genuine LLM classifications
    (not fallbacks) are kept as-is and NOT re-sent to the API. Only
    missing rows or rows that previously hit the fallback path are
    (re)computed. This matters because a full 400-row run at the
    enforced 13s/request pacing takes ~90 minutes, and the free tier
    is prone to transient rate-limit/server errors -- treating every
    run as all-or-nothing would be wasteful and fragile.

    Returns the number of records written to the final file.
    """
    dataset = load_dataset("STALEproj/STALE")
    rows = dataset["train"]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    existing_good: dict[str, dict] = {}
    if output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if not _is_fallback_record(rec):
                    existing_good[rec["uid"]] = rec
        print(f"Found {len(existing_good)} previously-succeeded records; will reuse them.")

    total_rows = len(rows)
    to_process = [row for row in rows if row["uid"] not in existing_good]
    print(f"{len(to_process)} of {total_rows} rows need (re)classification.")
    if to_process:
        est_minutes = round(len(to_process) * REQUEST_INTERVAL_SECONDS / 60, 1)
        print(f"Estimated time at {REQUEST_INTERVAL_SECONDS}s/request: ~{est_minutes} minutes.")

    all_records: dict[str, dict] = dict(existing_good)
    for i, row in enumerate(to_process, start=1):
        record = build_record(row)
        all_records[row["uid"]] = record
        status = "FALLBACK" if _is_fallback_record(record) else "ok"
        print(f"  [{i}/{len(to_process)}] uid={row['uid']} category={record['category']} ({status})")

        # Write progress incrementally so an interruption doesn't lose
        # already-completed work from this run.
        with open(output_path, "w", encoding="utf-8") as f:
            for r in rows:
                if r["uid"] in all_records:
                    f.write(json.dumps(all_records[r["uid"]], ensure_ascii=False) + "\n")

        if i < len(to_process):
            time.sleep(REQUEST_INTERVAL_SECONDS)

    # Final write in original dataset order (covers the case where
    # to_process was empty, i.e. everything was already good).
    with open(output_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(all_records[row["uid"]], ensure_ascii=False) + "\n")

    return len(all_records)


if __name__ == "__main__":
    n = build_stale_dataset()
    print(f"Wrote {n} records to {OUTPUT_PATH}")

    # Quick sanity summary
    tag_present = 0
    conflict_types: dict[str, int] = {}
    categories: dict[str, int] = {}
    low_confidence_uids: list[str] = []
    fallback_count = 0

    with open(OUTPUT_PATH, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["raw_ontology_tag"] is not None:
                tag_present += 1
            conflict_types[rec["conflict_type"]] = conflict_types.get(rec["conflict_type"], 0) + 1
            categories[rec["category"]] = categories.get(rec["category"], 0) + 1

            if rec["category_confidence"] < 0.5:
                low_confidence_uids.append(rec["uid"])
            if rec["category_confidence"] == 0.0 and "API call failed" in rec["category_reasoning"]:
                fallback_count += 1
            elif rec["category_confidence"] == 0.0 and "did not parse" in rec["category_reasoning"].lower():
                fallback_count += 1

    print(f"Records with raw_ontology_tag present: {tag_present}/{n}")
    print(f"Conflict type distribution: {conflict_types}")
    print(f"Category distribution: {categories}")
    print(f"Records with category_confidence < 0.5: {len(low_confidence_uids)}")
    print(f"Records that hit the classifier fallback (API failure/parse error): {fallback_count}")
    if fallback_count > 0:
        print(
            "WARNING: some records used the FACT fallback category due to a "
            "classification failure, not a genuine LLM judgment. Consider "
            "re-running the affected rows before using this dataset for evaluation."
        )