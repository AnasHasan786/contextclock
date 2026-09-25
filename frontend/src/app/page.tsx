"use client";

import { useState, type SubmitEvent as ReactSubmitEvent } from "react";
import {
  ApiError,
  MEMORY_CATEGORIES,
  createMemory,
  getMemoryScore,
  isCheckIncomplete,
  listMemories,
  parseServerDate,
  recordMemoryAccess,
  getScoresForScope,
  type Memory,
  type MemoryCategory,
  type MemoryWithScore,
  type StalenessLevel,
} from "@/lib/api";
import { capitalize } from "@/lib/format";
import { ghostButton, inputClass, labelClass, primaryButton } from "@/lib/ui";
import { MemoryEntry } from "@/components/MemoryEntry";
import { Spectrum } from "@/components/Spectrum";

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
      className="h-8 w-8 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9.5" />
      <path d="M12 3.5v1.5M12 19v1.5M3.5 12H5M19 12h1.5" />
      <path d="M12 7.5V12l3.25 2" />
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
  const [possiblyOutdated, setPossiblyOutdated] = useState<Record<string, boolean>>({});
  const [now, setNow] = useState(0);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scope: Scope = { userId: userId.trim(), agentId: agentId.trim() };
  const scopeReady = scope.userId !== "" && scope.agentId !== "";

  async function refresh(target: Scope) {
    const [list, restoredScores] = await Promise.all([
      listMemories(target.userId, target.agentId),
      getScoresForScope(target.userId, target.agentId),
    ]);
    setMemories(list);
    setLoadedScope(target);
    setNow(Date.now());

    const byId = new Map(list.map((m) => [m.id, m]));
    const merged: Record<string, MemoryWithScore> = {};
    const outdated: Record<string, boolean> = {};
    for (const [id, score] of Object.entries(restoredScores)) {
      const memory = byId.get(id);
      if (memory) {
        merged[id] = { memory, score };
        outdated[id] = true;
      }
    }
    setScores(merged);
    setPossiblyOutdated(outdated);
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
      setPossiblyOutdated((p) => without(p, id));
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

  // Only complete results count toward the spread; a failed check is "not checked".
  const counts: Record<StalenessLevel, number> = { fresh: 0, aging: 0, stale: 0, expired: 0 };
  for (const memory of newestFirst ?? []) {
    const result = scores[memory.id];
    if (result && !isCheckIncomplete(result.score)) counts[result.score.staleness_level] += 1;
  }

  const inner = "mx-auto w-full max-w-3xl px-6 sm:px-8";

  return (
    <div className="lg:flex lg:h-screen lg:overflow-hidden">
      <aside className="border-b border-rule bg-surface lg:h-full lg:w-[22rem] lg:shrink-0 lg:overflow-y-auto lg:border-b-0 lg:border-r">
        <div className="flex min-h-full flex-col gap-8 px-6 py-8">
          <div>
            <div className="flex items-center gap-3">
              <ClockMark />
              <h1 className="font-serif text-3xl leading-none">ContextClock</h1>
            </div>
            <p className="mt-3 text-sm text-muted">
              Find out which of an agent&apos;s memories have gone out of date.
            </p>
          </div>

          <section>
            <h2 className="text-sm font-semibold">Scope</h2>
            <p className="mt-1 text-xs text-muted">Every memory belongs to one user and one agent.</p>
            <div className="mt-3 grid grid-cols-2 gap-3">
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
            </div>
            <button
              type="button"
              className={`${ghostButton} mt-3 w-full`}
              onClick={handleLoad}
              disabled={busy || !scopeReady}
            >
              Load memories
            </button>
          </section>

          <section>
            <h2 className="text-sm font-semibold">Add a memory</h2>
            <form onSubmit={handleCreate} className="mt-3 space-y-3">
              <div>
                <label htmlFor="content" className={labelClass}>
                  What did the agent learn?
                </label>
                <textarea
                  id="content"
                  rows={4}
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
                className={`${primaryButton} w-full`}
                disabled={busy || !scopeReady || content.trim() === ""}
              >
                Add memory
              </button>
            </form>
          </section>

          <p className="mt-auto text-xs text-muted">
            Memories live in the server&apos;s RAM, so restarting the backend clears them.
          </p>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col lg:h-full">
        <header className="border-b border-rule pb-6 pt-8">
          <div className={inner}>
            <h2 className="font-serif text-3xl leading-none">Memories</h2>
            <p className="mt-3 text-sm text-muted">
              {newestFirst === null || loadedScope === null
                ? "No scope loaded yet."
                : `${newestFirst.length} ${newestFirst.length === 1 ? "memory" : "memories"} for ${loadedScope.userId} with ${loadedScope.agentId}. Checking compares a memory with newer ones using Gemini, so it can take a few seconds.`}
            </p>
            {newestFirst !== null && (
              <Spectrum counts={counts} total={newestFirst.length} />
            )}
            {error && (
              <div
                role="alert"
                className="mt-5 rounded-xl border border-expired/40 bg-expired/10 px-4 py-3 text-sm text-expired"
              >
                {error}
              </div>
            )}
          </div>
        </header>

        <div className="flex-1 lg:overflow-y-auto">
          <div className={`${inner} py-8`}>
            {newestFirst === null || loadedScope === null ? (
              <div className="rounded-2xl border border-dashed border-rule p-8">
                <p className="font-serif text-xl">No scope loaded</p>
                <p className="mt-1 max-w-[46ch] text-sm text-muted">
                  Load a scope to see its memories. Anything you add appears here, newest first.
                </p>
              </div>
            ) : newestFirst.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-rule p-8">
                <p className="font-serif text-xl">Nothing here yet</p>
                <p className="mt-1 max-w-[46ch] text-sm text-muted">
                  {loadedScope.userId} with {loadedScope.agentId} has no memories. Add one to start
                  the timeline.
                </p>
              </div>
            ) : (
              <ol>
                {newestFirst.map((memory) => (
                  <MemoryEntry
                    key={memory.id}
                    memory={memory}
                    result={scores[memory.id]}
                    possiblyOutdated={Boolean(possiblyOutdated[memory.id])}
                    now={now}
                    pending={pending[memory.id]}
                    onCheck={handleCheck}
                    onMarkUsed={handleMarkUsed}
                  />
                ))}
              </ol>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}