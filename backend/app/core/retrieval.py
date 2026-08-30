"""
Candidate retrieval for contradiction detection (Phase 2).

Given a new memory, find a small set of existing memories worth
sending to the LLM for contradiction analysis. This step is entirely
deterministic -- no LLM calls happen here.

Design rationale (see thesis Methods section):
- Hard filter: same user_id AND same agent_id (never compare across
  users -- privacy/correctness boundary, not just relevance).
- Primary ranking: semantic similarity via sentence-transformers.
  Category is deliberately NOT used as a hard filter, because a
  cross-category contradiction (e.g. a PREFERENCE memory conflicting
  with a later FACT memory) would otherwise never be considered.
- Secondary boost: same-category candidates receive a small score
  boost, since same-category pairs are more likely to concern the
  same underlying fact slot. This uses category as a *supporting*
  signal rather than the sole signal, in response to prior findings
  that similarity search alone cannot reliably distinguish
  contradiction from unrelated/paraphrased content (Yadav, 2026).
- Minimum similarity threshold + top-K cap: controls both false
  positives (obviously unrelated pairs) and API cost (Gemini calls
  in Step 5+ are the expensive part of the pipeline).
"""

from dataclasses import dataclass
from sentence_transformers import SentenceTransformer, util

from app.models.memory import Memory

# Loaded once at module import time -- reused across all calls.
# all-MiniLM-L6-v2 is small, fast, and sufficient for this kind of
# short-sentence similarity task (not a heavy semantic search job).
_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# Tunable constants -- report these explicitly in your Methods
# section, since they are heuristic choices, not derived values.
MIN_SIMILARITY_THRESHOLD = 0.35
TOP_K_CANDIDATES = 3
CATEGORY_MATCH_BOOST = 0.10


@dataclass
class RetrievalCandidate:
    memory: Memory
    similarity_score: float
    boosted_score: float
    same_category: bool


def find_candidate_memories(
    new_memory: Memory,
    existing_memories: list[Memory],
) -> list[RetrievalCandidate]:
    """
    Return up to TOP_K_CANDIDATES existing memories worth comparing
    against `new_memory` for contradiction detection.

    This function does NOT call any LLM. It is pure retrieval.
    """
    # Step 1 -- hard filter: same user, same agent, exclude self.
    same_scope = [
        m
        for m in existing_memories
        if m.user_id == new_memory.user_id
        and m.agent_id == new_memory.agent_id
        and m.id != new_memory.id
    ]

    if not same_scope:
        return []

    # Step 2 -- compute semantic similarity for every candidate in scope.
    new_embedding = _embedding_model.encode(new_memory.content, convert_to_tensor=True)
    candidate_texts = [m.content for m in same_scope]
    candidate_embeddings = _embedding_model.encode(candidate_texts, convert_to_tensor=True)

    similarities = util.cos_sim(new_embedding, candidate_embeddings)[0]

    # Step 3 -- apply category boost, threshold, and rank.
    scored: list[RetrievalCandidate] = []
    for memory, raw_score in zip(same_scope, similarities):
        raw_score = float(raw_score)
        same_category = memory.category == new_memory.category
        boosted = raw_score + (CATEGORY_MATCH_BOOST if same_category else 0.0)

        if boosted >= MIN_SIMILARITY_THRESHOLD:
            scored.append(
                RetrievalCandidate(
                    memory=memory,
                    similarity_score=raw_score,
                    boosted_score=boosted,
                    same_category=same_category,
                )
            )

    # Step 4 -- rank by boosted score, cap at top-K.
    scored.sort(key=lambda c: c.boosted_score, reverse=True)
    return scored[:TOP_K_CANDIDATES]