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
- MemoryCategory is NOT assigned here. Only ~12% of explanations carry
  an extractable ontology-style tag (verified empirically, and not
  concentrated in either conflict type), so string-parsing the
  explanation field is not a viable primary mapping strategy. Category
  assignment is deferred to a separate LLM classification pass using
  the same classifier ContextClock's production pipeline uses, for
  methodological consistency. Where an ontology tag IS present, it is
  preserved in `raw_ontology_tag` purely as a non-authoritative
  cross-check, never as ground truth.
- All 400 STALE rows are positive (genuine contradiction) pairs --
  verified by manual inspection of flagged rows. STALE contains no
  negative / non-conflicting examples. This script does not invent
  any; the absence of negatives is a documented evaluation limitation,
  to be addressed separately with ContextClock's own synthetic
  UNRELATED/CONSISTENT test cases.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from datasets import load_dataset

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

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


def build_record(row: dict) -> dict:
    """Convert a single raw STALE row into a ContextClock evaluation record."""
    old_idx, new_idx = row["relevant_session_index"]
    old_timestamp = _parse_timestamp(row["timestamps"][old_idx])
    new_timestamp = _parse_timestamp(row["timestamps"][new_idx])
    gap_days = (new_timestamp - old_timestamp).days

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
    }


def build_stale_dataset(output_path: Path = OUTPUT_PATH) -> int:
    """
    Load STALE, convert all rows, write to JSONL.
    Returns the number of records written.
    """
    dataset = load_dataset("STALEproj/STALE")
    rows = dataset["train"]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for row in rows:
            record = build_record(row)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    return count


if __name__ == "__main__":
    n = build_stale_dataset()
    print(f"Wrote {n} records to {OUTPUT_PATH}")

    # Quick sanity summary
    tag_present = 0
    conflict_types: dict[str, int] = {}
    with open(OUTPUT_PATH, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["raw_ontology_tag"] is not None:
                tag_present += 1
            conflict_types[rec["conflict_type"]] = conflict_types.get(rec["conflict_type"], 0) + 1

    print(f"Records with raw_ontology_tag present: {tag_present}/{n}")
    print(f"Conflict type distribution: {conflict_types}")