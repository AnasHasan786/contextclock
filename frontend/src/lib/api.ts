export const MEMORY_CATEGORIES = [
    "employment",
    "location",
    "relationship",
    "preference",
    "personal",
    "fact",
] as const;

export type MemoryCategory = (typeof MEMORY_CATEGORIES)[number];

export type StalenessLevel = "fresh" | "aging" | "stale" | "expired";

export interface Memory {
    id: string;
    content: string;
    category: MemoryCategory;
    user_id: string;
    agent_id: string;
    created_at: string;
    updated_at: string;
    last_accessed_at: string | null;
    access_count: number;
}

export interface MemoryCreate {
    content: string;
    category: MemoryCategory;
    user_id: string;
    agent_id: string;
}

export interface StalenessScore {
    memory_id: string;
    time_decay_score: number;
    contradiction_score: number;
    access_anomaly_score: number;
    final_score: number;
    staleness_level: StalenessLevel;
    computed_at: string;
    explanation: string;
}

export interface MemoryWithScore {
    memory: Memory;
    score: StalenessScore;
}

/**
 * When contradiction lookups fail (for example Gemini returns a 503) and
 * nothing else was found, the backend starts its contradiction reasoning with
 * this text (CHECK_INCOMPLETE_PREFIX in backend/app/core/fallback.py). The
 * reasoning is appended to StalenessScore.explanation after this label.
 */
const CHECK_INCOMPLETE_MARKER = "Contradiction detail: Contradiction check incomplete";

export function isCheckIncomplete(score: StalenessScore): boolean {
    return score.explanation.includes(CHECK_INCOMPLETE_MARKER);
}

/**
 * The backend stores naive UTC datetimes, so they serialize without a
 * timezone suffix. new Date() would read such a string as LOCAL time and
 * shift every timestamp by your UTC offset. This treats them as UTC.
 */
export function parseServerDate(value: string): Date {
    const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(value);
    return new Date(hasZone ? value : `${value}Z`);
}

export class ApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
        super(message);
        this.name = "ApiError";
        this.status = status;
    }
}

async function readErrorMessage(response: Response): Promise<string> {
    try {
        const body = await response.json();
        if (typeof body?.detail === "string") return body.detail;
        if (Array.isArray(body?.detail)) {
            return body.detail
                .map((d: { msg?: string }) => d.msg ?? "Invalid input")
                .join("; ");
        }
    } catch {
        // Response body wasn't JSON; fall through to the generic message.
    }
    return `Request failed with status ${response.status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const base = process.env.NEXT_PUBLIC_API_URL;
    if (!base) {
        throw new Error(
            "NEXT_PUBLIC_API_URL is not set. Add it to frontend/.env.local and restart `npm run dev`."
        );
    }

    let response: Response;
    try {
        response = await fetch(`${base}${path}`, { cache: "no-store", ...init });
    } catch {
        throw new ApiError(0, `Cannot reach the API at ${base}. Is the backend running?`);
    }

    if (!response.ok) {
        throw new ApiError(response.status, await readErrorMessage(response));
    }
    return (await response.json()) as T;
}

export function createMemory(payload: MemoryCreate): Promise<Memory> {
    return request<Memory>("/memories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
}

export function listMemories(userId: string, agentId: string): Promise<Memory[]> {
    const params = new URLSearchParams({ user_id: userId, agent_id: agentId });
    return request<Memory[]>(`/memories?${params}`);
}

/** Read-only on the backend: never bumps access_count. */
export function getMemoryScore(memoryId: string): Promise<MemoryWithScore> {
    return request<MemoryWithScore>(`/memories/${encodeURIComponent(memoryId)}/score`);
}

/** Call only when a memory is genuinely used; feeds the access-anomaly signal. */
export function recordMemoryAccess(memoryId: string): Promise<Memory> {
    return request<Memory>(`/memories/${encodeURIComponent(memoryId)}/access`, {
        method: "POST",
    });
}

export function getScoresForScope(
    userId: string,
    agentId: string
): Promise<Record<string, StalenessScore>> {
    const params = new URLSearchParams({ user_id: userId, agent_id: agentId });
    return request<Record<string, StalenessScore>>(`/memories/scores?${params}`);
}