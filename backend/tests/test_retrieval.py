from datetime import datetime

from app.models.memory import Memory, MemoryCategory
from app.core.retrieval import find_candidate_memories, MIN_SIMILARITY_THRESHOLD, TOP_K_CANDIDATES


def make_memory(id, content, category, user_id="u1", agent_id="a1", created_at=None):
    return Memory(
        id=id,
        content=content,
        category=category,
        user_id=user_id,
        agent_id=agent_id,
        created_at=created_at or datetime(2026, 1, 1),
    )


def test_excludes_other_users():
    new_memory = make_memory("new", "User works at Google.", MemoryCategory.EMPLOYMENT, user_id="u1")
    other_user_memory = make_memory("other", "User works at Google.", MemoryCategory.EMPLOYMENT, user_id="u2")

    candidates = find_candidate_memories(new_memory, [other_user_memory])

    assert candidates == []


def test_excludes_other_agents():
    new_memory = make_memory("new", "User works at Google.", MemoryCategory.EMPLOYMENT, agent_id="a1")
    other_agent_memory = make_memory("other", "User works at Google.", MemoryCategory.EMPLOYMENT, agent_id="a2")

    candidates = find_candidate_memories(new_memory, [other_agent_memory])

    assert candidates == []


def test_excludes_self():
    memory = make_memory("m1", "User works at Google.", MemoryCategory.EMPLOYMENT)

    candidates = find_candidate_memories(memory, [memory])

    assert candidates == []


def test_finds_semantically_similar_same_category():
    new_memory = make_memory("new", "User now works at Microsoft.", MemoryCategory.EMPLOYMENT)
    related = make_memory("related", "User works at Google.", MemoryCategory.EMPLOYMENT)
    unrelated = make_memory("unrelated", "User enjoys hiking on weekends.", MemoryCategory.PREFERENCE)

    candidates = find_candidate_memories(new_memory, [related, unrelated])
    candidate_ids = [c.memory.id for c in candidates]

    assert "related" in candidate_ids
    assert "unrelated" not in candidate_ids


def test_same_category_receives_boost():
    new_memory = make_memory("new", "User works at Google.", MemoryCategory.EMPLOYMENT)
    same_category = make_memory("same_cat", "User is employed at Alphabet.", MemoryCategory.EMPLOYMENT)
    diff_category = make_memory("diff_cat", "User is employed at Alphabet.", MemoryCategory.FACT)

    candidates = find_candidate_memories(new_memory, [same_category, diff_category])
    same_cat_candidate = next(c for c in candidates if c.memory.id == "same_cat")
    diff_cat_candidate = next(c for c in candidates if c.memory.id == "diff_cat")

    # Same raw text, different category -- same_category's boosted score
    # must be strictly higher despite identical similarity_score.
    assert same_cat_candidate.similarity_score == diff_cat_candidate.similarity_score
    assert same_cat_candidate.boosted_score > diff_cat_candidate.boosted_score
    assert same_cat_candidate.same_category is True
    assert diff_cat_candidate.same_category is False


def test_respects_top_k_cap():
    new_memory = make_memory("new", "User works at Google.", MemoryCategory.EMPLOYMENT)
    many_similar = [
        make_memory(f"m{i}", "User works at Google as an engineer.", MemoryCategory.EMPLOYMENT)
        for i in range(TOP_K_CANDIDATES + 5)
    ]

    candidates = find_candidate_memories(new_memory, many_similar)

    assert len(candidates) <= TOP_K_CANDIDATES


def test_empty_existing_memories_returns_empty():
    new_memory = make_memory("new", "User works at Google.", MemoryCategory.EMPLOYMENT)

    candidates = find_candidate_memories(new_memory, [])

    assert candidates == []


def test_below_threshold_excluded():
    new_memory = make_memory("new", "User works at Google.", MemoryCategory.EMPLOYMENT)
    clearly_unrelated = make_memory(
        "unrelated", "The weather today is sunny with a light breeze.", MemoryCategory.FACT
    )

    candidates = find_candidate_memories(new_memory, [clearly_unrelated])

    for c in candidates:
        assert c.boosted_score >= MIN_SIMILARITY_THRESHOLD
    # This pair should realistically produce near-zero similarity.
    assert clearly_unrelated.id not in [c.memory.id for c in candidates]