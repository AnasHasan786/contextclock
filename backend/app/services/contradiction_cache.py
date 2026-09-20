"""
In-memory cache of Gemini contradiction verdicts.

Keyed by (old_memory_id, new_memory_id). Memories are immutable (there is
no update route), so a verdict for a given pair never goes stale. Time
decay and access anomaly are NOT cached; they are recomputed on every
score request.

If an update route is ever added, entries involving the edited memory
must be invalidated.

detect_contradiction() never raises: on an API error or an unparseable
response it returns UNRELATED / 0.0 with a recognizable prefix in
`reasoning`. Those fallbacks must not be cached, otherwise one transient
failure (or a hit on the daily quota) would stick until restart.
"""

from app.core.contradiction import ContradictionResult, detect_contradiction
from app.models.memory import Memory

# Must match the fallback messages in contradiction.detect_contradiction().
_FALLBACK_PREFIXES = ("API call failed", "Response did not parse to schema")


def _is_fallback(result: ContradictionResult) -> bool:
    return result.reasoning.startswith(_FALLBACK_PREFIXES)


class ContradictionCache:
    def __init__(self) -> None:
        self._verdicts: dict[tuple[str, str], ContradictionResult] = {}

    def __call__(self, old_memory: Memory, new_memory: Memory) -> ContradictionResult:
        """Same call shape as detect_contradiction(old_memory=, new_memory=),
        so it can be passed anywhere a detector is expected. Worst case under
        concurrent requests is one duplicate Gemini call, never a wrong result."""
        key = (old_memory.id, new_memory.id)
        cached = self._verdicts.get(key)
        if cached is not None:
            return cached

        result = detect_contradiction(old_memory=old_memory, new_memory=new_memory)
        if not _is_fallback(result):
            self._verdicts[key] = result
        return result

    def __len__(self) -> int:
        return len(self._verdicts)