from datetime import datetime, timedelta, timezone

from app.models.memory import Memory, MemoryCategory
from app.services.memory_store import MemoryStore


def make_memory(
    memory_id="mem_1",
    user_id="user_001",
    agent_id="agent_001",
    content="User works at Google",
    category=MemoryCategory.EMPLOYMENT,
) -> Memory:
    """Helper to build Memory objects for tests."""
    return Memory(
        id=memory_id,
        content=content,
        category=category,
        user_id=user_id,
        agent_id=agent_id,
    )


def test_add_and_get_round_trip():
    """A memory added to the store can be fetched back by id."""
    store = MemoryStore()
    memory = make_memory()
    store.add(memory)
    fetched = store.get(memory.id)
    assert fetched is not None
    assert fetched.id == memory.id
    assert fetched.content == memory.content
    print("✓ add() then get() returns the same memory")


def test_get_missing_id_returns_none():
    """Fetching an id that was never added should not raise."""
    store = MemoryStore()
    assert store.get("does-not-exist") is None
    print("✓ get() on unknown id returns None")


def test_list_for_scope_only_returns_matching_user_and_agent():
    """Memories from a different user or agent must never leak in."""
    store = MemoryStore()
    store.add(make_memory(memory_id="m1", user_id="u1", agent_id="a1"))
    store.add(make_memory(memory_id="m2", user_id="u1", agent_id="a1"))
    store.add(
        make_memory(memory_id="m3", user_id="u1", agent_id="a2")
    )  # different agent
    store.add(
        make_memory(memory_id="m4", user_id="u2", agent_id="a1")
    )  # different user

    scoped = store.list_for_scope("u1", "a1")
    scoped_ids = {m.id for m in scoped}

    assert scoped_ids == {"m1", "m2"}
    print(f"✓ list_for_scope() isolates by (user_id, agent_id): {scoped_ids}")


def test_list_for_scope_empty_when_no_match():
    """A scope with no memories returns an empty list, not an error."""
    store = MemoryStore()
    store.add(make_memory(memory_id="m1", user_id="u1", agent_id="a1"))
    assert store.list_for_scope("nobody", "nothing") == []
    print("✓ list_for_scope() with no matches returns []")


def test_record_access_increments_count_and_sets_timestamp():
    """record_access should bump access_count and stamp last_accessed_at."""
    store = MemoryStore()
    memory = make_memory()
    store.add(memory)

    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    updated = store.record_access(memory.id)

    assert updated is not None
    assert updated.access_count == 1
    assert updated.last_accessed_at is not None
    assert updated.last_accessed_at.replace(tzinfo=timezone.utc) >= before

    store.record_access(memory.id)
    assert store.get(memory.id).access_count == 2
    print("✓ record_access() increments count and updates last_accessed_at")


def test_record_access_on_missing_id_returns_none():
    """Recording access on a nonexistent memory should not raise."""
    store = MemoryStore()
    assert store.record_access("does-not-exist") is None
    print("✓ record_access() on unknown id returns None")
