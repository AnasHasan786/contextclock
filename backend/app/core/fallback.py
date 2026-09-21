"""
Recognizing the safe fallback that contradiction.detect_contradiction()
returns when the Gemini call fails or its response can't be parsed.

detect_contradiction() never raises. A failed call comes back as
UNRELATED / 0.0 with a recognizable prefix in `reasoning`, which is
indistinguishable from a genuine "no contradiction" verdict unless the
caller checks. The cache and the scorer both do.
"""

from app.core.contradiction import ContradictionResult

# Must match the fallback messages in contradiction.detect_contradiction().
FALLBACK_PREFIXES = ("API call failed", "Response did not parse to schema")

# Start of the reasoning string resolve_contradiction_score() returns when
# comparisons failed and nothing else was found. The frontend looks for it.
CHECK_INCOMPLETE_PREFIX = "Contradiction check incomplete"


def is_fallback(result: ContradictionResult) -> bool:
    return result.reasoning.startswith(FALLBACK_PREFIXES)