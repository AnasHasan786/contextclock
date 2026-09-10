"""
Baseline systems for Phase 2 evaluation (Step 9).

Three baselines to compare against ContextClock's full pipeline
(retrieval + LLM contradiction detection, Steps 3-7). Each targets a
specific claim from the literature review rather than being an
arbitrary strawman:

1. Recency-only
   Ignores memory content entirely. A memory is considered fully
   stale (score 1.0) if ANY newer memory exists in the same category
   for the same user/agent -- regardless of whether that newer
   memory is actually about the same fact. Represents the simplest
   "most recent wins" approach: no decay math, no semantic
   understanding.

2. Similarity-only (naive deterministic)
   Uses raw cosine similarity (same embedding model as retrieval.py)
   directly AS the contradiction score -- no LLM involved. Exists
   specifically to test, on ContextClock's own data, the failure
   mode reported by Yadav (2026) MemStrata: similarity alone cannot
   reliably separate contradiction from paraphrase/unrelated content,
   since a value-flip contradiction is not necessarily more
   dissimilar than a harmless restatement.

3. Always-LLM (no retrieval filtering)
   Skips the deterministic retrieval/filtering stage (Step 3)
   entirely and asks Gemini to judge EVERY newer memory in scope,
   not just the top-K most similar candidates. Isolates what
   retrieval-based filtering actually buys: accuracy, cost, both, or
   neither.
"""

from app.models.memory import Memory
from app.core.retrieval import _embedding_model
from app.core.contradiction import detect_contradiction, MemoryRelationship
from sentence_transformers import util


def _newer_same_scope(memory: Memory, existing_memories: list[Memory]) -> list[Memory]:
    """Shared filter used by all three baselines: same user/agent, created after `memory`, excluding self."""
    return [
        m for m in existing_memories
        if m.user_id == memory.user_id
        and m.agent_id == memory.agent_id
        and m.created_at > memory.created_at
        and m.id != memory.id
    ]


def recency_only_score(memory: Memory, existing_memories: list[Memory]) -> tuple[float, str]:
    newer_same_category = [
        m for m in _newer_same_scope(memory, existing_memories)
        if m.category == memory.category
    ]
    if newer_same_category:
        return 1.0, f"Newer same-category memory exists: {newer_same_category[0].id!r}."
    return 0.0, "No newer same-category memory exists."


def similarity_only_score(memory: Memory, existing_memories: list[Memory]) -> tuple[float, str]:
    candidates = _newer_same_scope(memory, existing_memories)
    if not candidates:
        return 0.0, "No newer memories to compare."

    memory_embedding = _embedding_model.encode(memory.content, convert_to_tensor=True)
    candidate_embeddings = _embedding_model.encode([m.content for m in candidates], convert_to_tensor=True)
    similarities = util.cos_sim(memory_embedding, candidate_embeddings)[0]

    best_idx = int(similarities.argmax())
    best_score = float(similarities[best_idx])
    best_memory = candidates[best_idx]

    return best_score, f"Highest raw similarity ({best_score:.3f}) vs memory {best_memory.id!r} ({best_memory.content!r})."


def always_llm_score(memory: Memory, existing_memories: list[Memory]) -> tuple[float, str, int]:
    """
    Returns (score, reasoning, num_api_calls_made). The call count is
    reported so Step 11-13's cost/latency comparison can quantify
    exactly how many more Gemini calls this baseline makes versus
    ContextClock's filtered retrieval.
    """
    candidates = _newer_same_scope(memory, existing_memories)
    if not candidates:
        return 0.0, "No newer memories to compare.", 0

    best_score = 0.0
    best_reasoning = "No contradiction or supersession detected among any newer memory."
    calls_made = 0

    for candidate in candidates:
        result = detect_contradiction(old_memory=memory, new_memory=candidate)
        calls_made += 1
        if result.relationship in (MemoryRelationship.CONTRADICTS, MemoryRelationship.SUPERSEDES):
            if result.score > best_score:
                best_score = result.score
                best_reasoning = f"[{result.relationship.value}] vs memory {candidate.id!r}: {result.reasoning}"

    return best_score, best_reasoning, calls_made