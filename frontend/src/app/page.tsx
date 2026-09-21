"use client";

import { useState, type SubmitEvent as ReactSubmitEvent } from "react";
import {
  ApiError,
  MEMORY_CATEGORIES,
  createMemory,
  getMemoryScore,
  listMemories,
  parseServerDate,
  recordMemoryAccess,
  type Memory,
  type MemoryCategory,
  type MemoryWithScore,
} from "@/lib/api";
import { capitalize } from "@/lib/format";
import { ghostButton, inputClass, labelClass, primaryButton } from "@/lib/ui";
import { MemoryEntry } from "@/components/MemoryEntry";

interface Scope {
  userId: string;
  agentId: string;
}

function messageOf(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) {
    return "That memory no longer exists on the server. The backend keeps memories in RAM, so a restart clears them. Load memories again.";
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}

function without<T>(record: Record<string, T>, key: string): Record<string, T> {
  const next = { ...record };
  delete next[key];
  return next;
}

function ClockMark() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-7 w-7 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

export default function Home() {
  const [userId, setUserId] = useState("demo-user");
  const [agentId, setAgentId] = useState("demo-agent");
  const [content, setContent] = useState("");
  const [category, setCategory] = useState<MemoryCategory>("employment");

  const [memories, setMemories] = useState<Memory[] | null>(null);
  const [loadedScope, setLoadedScope] = useState<Scope | null>(null);
  const [scores, setScores] = useState<Record<string, MemoryWithScore>>({});
  const [pending, setPending] = useState<Record<string, "check" | "use">>({});
  const [now, setNow] = useState(0);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scope: Scope = { userId: userId.trim(), agentId: agentId.trim() };
  const scopeReady = scope.userId !== "" && scope.agentId !== "";

  async function refresh(target: Scope) {
    const list = await listMemories(target.userId, target.agentId);
    setMemories(list);
    setLoadedScope(target);
    setNow(Date.now());
  }

  async function handleLoad() {
    if (!scopeReady) return;
    setBusy(true);
    setError(null);
    try {
      await refresh(scope);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreate(event: ReactSubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!scopeReady || content.trim() === "") return;
    setBusy(true);
    setError(null);
    try {
      await createMemory({
        content: content.trim(),
        category,
        user_id: scope.userId,
        agent_id: scope.agentId,
      });
      setContent("");
      await refresh(scope);
      // A new memory can contradict any older one, so earlier results are out of date.
      setScores({});
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleCheck(id: string) {
    setPending((p) => ({ ...p, [id]: "check" }));
    setError(null);
    try {
      const result = await getMemoryScore(id);
      setScores((s) => ({ ...s, [id]: result }));
      setNow(Date.now());
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setPending((p) => without(p, id));
    }
  }

  async function handleMarkUsed(id: string) {
    setPending((p) => ({ ...p, [id]: "use" }));
    setError(null);
    try {
      const updated = await recordMemoryAccess(id);
      setMemories((list) => list && list.map((m) => (m.id === id ? updated : m)));
      setNow(Date.now());
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setPending((p) => without(p, id));
    }
  }

  const newestFirst = memories
    ? [...memories].sort(
      (a, b) =>
        parseServerDate(b.created_at).getTime() - parseServerDate(a.created_at).getTime(),
    )
    : null;

  return (
    <main className="mx-auto max-w-5xl px-5 py-12 sm:py-16">
      <header className="flex items-start gap-3">
        <ClockMark />
        <div>
          <h1 className="font-serif text-4xl leading-none">ContextClock</h1>
          <p className="mt-2 max-w-[52ch] text-muted">
            Find out which of an agent&apos;s memories have gone out of date.
          </p>
        </div>
      </header>

      {error && (
        <div
          role="alert"
          className="mt-8 rounded-xl border border-expired/40 bg-expired/10 px-4 py-3 text-sm text-expired"
        >
          {error}
        </div>
      )}

      <div className="mt-12 grid gap-12 lg:grid-cols-[19rem_1fr] lg:gap-16">
        <div className="space-y-10 lg:sticky lg:top-10 lg:self-start">
          <section>
            <h2 className="font-serif text-2xl">Scope</h2>
            <p className="mt-1 text-sm text-muted">
              Every memory belongs to one user and one agent.
            </p>
            <div className="mt-4 space-y-3">
              <div>
                <label htmlFor="user-id" className={labelClass}>
                  User ID
                </label>
                <input
                  id="user-id"
                  className={inputClass}
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="agent-id" className={labelClass}>
                  Agent ID
                </label>
                <input
                  id="agent-id"
                  className={inputClass}
                  value={agentId}
                  onChange={(e) => setAgentId(e.target.value)}
                />
              </div>
              <button
                type="button"
                className={ghostButton}
                onClick={handleLoad}
                disabled={busy || !scopeReady}
              >
                Load memories
              </button>
            </div>
          </section>

          <section>
            <h2 className="font-serif text-2xl">Add a memory</h2>
            <form onSubmit={handleCreate} className="mt-4 space-y-3">
              <div>
                <label htmlFor="content" className={labelClass}>
                  What did the agent learn?
                </label>
                <textarea
                  id="content"
                  rows={3}
                  className={`${inputClass} resize-y`}
                  placeholder="User works at Google"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="category" className={labelClass}>
                  Category
                </label>
                <select
                  id="category"
                  className={inputClass}
                  value={category}
                  onChange={(e) => setCategory(e.target.value as MemoryCategory)}
                >
                  {MEMORY_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {capitalize(c)}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="submit"
                className={primaryButton}
                disabled={busy || !scopeReady || content.trim() === ""}
              >
                Add memory
              </button>
            </form>
          </section>
        </div>

        <section aria-labelledby="memories-heading" className="min-w-0">
          <h2 id="memories-heading" className="font-serif text-2xl">
            Memories
          </h2>

          {newestFirst === null || loadedScope === null ? (
            <div className="mt-5 rounded-2xl border border-dashed border-rule p-8">
              <p className="font-serif text-xl">No scope loaded</p>
              <p className="mt-1 max-w-[46ch] text-sm text-muted">
                Load a scope to see its memories. Anything you add appears here, newest first.
              </p>
            </div>
          ) : newestFirst.length === 0 ? (
            <div className="mt-5 rounded-2xl border border-dashed border-rule p-8">
              <p className="font-serif text-xl">Nothing here yet</p>
              <p className="mt-1 max-w-[46ch] text-sm text-muted">
                {loadedScope.userId} with {loadedScope.agentId} has no memories. Add one to start
                the timeline.
              </p>
            </div>
          ) : (
            <>
              <p className="mt-1 text-sm text-muted">
                {newestFirst.length} {newestFirst.length === 1 ? "memory" : "memories"} for{" "}
                {loadedScope.userId} with {loadedScope.agentId}. Checking compares a memory with
                newer ones using Gemini, so it can take a few seconds.
              </p>
              <ol className="mt-8 ml-[7px] border-l border-rule">
                {newestFirst.map((memory) => (
                  <MemoryEntry
                    key={memory.id}
                    memory={memory}
                    result={scores[memory.id]}
                    now={now}
                    pending={pending[memory.id]}
                    onCheck={handleCheck}
                    onMarkUsed={handleMarkUsed}
                  />
                ))}
              </ol>
            </>
          )}
        </section>
      </div>
    </main>
  );
}