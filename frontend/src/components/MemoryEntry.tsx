import {
  isCheckIncomplete,
  parseServerDate,
  type Memory,
  type MemoryWithScore,
} from "@/lib/api";
import {
  LEVEL_STYLES,
  capitalize,
  describeUse,
  formatAge,
  formatDateTime,
} from "@/lib/format";
import { ghostButton, primaryButton } from "@/lib/ui";
import { ScorePanel } from "./ScorePanel";

interface Props {
  memory: Memory;
  result?: MemoryWithScore;
  now: number;
  pending?: "check" | "use";
  onCheck: (id: string) => void;
  onMarkUsed: (id: string) => void;
}

/**
 * One entry on the timeline. The node on the spine is hollow until the
 * memory has been checked, then it takes the color of its staleness level
 * (or stays a hollow amber ring if the check could not finish).
 */
export function MemoryEntry({ memory, result, now, pending, onCheck, onMarkUsed }: Props) {
  const created = parseServerDate(memory.created_at);
  const level = result ? LEVEL_STYLES[result.score.staleness_level] : null;
  const incomplete = result !== undefined && isCheckIncomplete(result.score);
  const nodeClass =
    level === null
      ? "border-muted bg-paper"
      : incomplete
        ? "border-aging bg-paper"
        : `${level.border} ${level.solid}`;

  return (
    <li className="relative pb-10 pl-8 last:pb-0">
      <span
        aria-hidden="true"
        className={`absolute -left-[7.5px] top-1 h-3.5 w-3.5 rounded-full border-2 ${nodeClass}`}
      />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="rounded-full border border-rule px-2.5 py-0.5 text-xs text-muted">
          {capitalize(memory.category)}
        </span>
        <time
          dateTime={created.toISOString()}
          title={formatDateTime(created)}
          className="text-xs text-muted"
        >
          Added {formatAge(created, now)}
        </time>
      </div>

      <p className="mt-2 max-w-[62ch] font-serif text-xl leading-snug">{memory.content}</p>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={primaryButton}
          onClick={() => onCheck(memory.id)}
          disabled={pending !== undefined}
          aria-busy={pending === "check"}
        >
          {pending === "check"
            ? "Checking…"
            : incomplete
              ? "Try again"
              : result
                ? "Check again"
                : "Check staleness"}
        </button>
        <button
          type="button"
          className={ghostButton}
          onClick={() => onMarkUsed(memory.id)}
          disabled={pending !== undefined}
          aria-busy={pending === "use"}
        >
          {pending === "use" ? "Saving…" : "Mark as used"}
        </button>
        <span className="text-xs text-muted">
          {describeUse(memory.access_count, memory.last_accessed_at, now)}
        </span>
      </div>

      {result && <ScorePanel score={result.score} now={now} />}
    </li>
  );
}