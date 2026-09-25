import type { StalenessLevel } from "@/lib/api";
import { LEVEL_STYLES } from "@/lib/format";

const ORDER: StalenessLevel[] = ["fresh", "aging", "stale", "expired"];

interface Props {
    counts: Record<StalenessLevel, number>;
    total: number;
}

/**
 * A single bar showing how the memories checked so far are spread across the
 * staleness levels. The unfilled remainder is memories not checked yet.
 */
export function Spectrum({ counts, total }: Props) {
    if (total === 0) return null;

    const present = ORDER.filter((level) => counts[level] > 0);
    const checked = present.reduce((sum, level) => sum + counts[level], 0);
    const summary = present.map((level) => `${counts[level]} ${LEVEL_STYLES[level].label.toLowerCase()}`);

    return (
        <div className="mt-5">
            <div
                role="img"
                aria-label={`${checked} of ${total} memories checked${summary.length ? `: ${summary.join(", ")}` : ""}`}
                className="flex h-2 overflow-hidden rounded-full bg-rule"
            >
                {present.map((level) => (
                    <div
                        key={level}
                        className={LEVEL_STYLES[level].solid}
                        style={{ width: `${(counts[level] / total) * 100}%` }}
                    />
                ))}
            </div>
            <ul className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
                {present.map((level) => (
                    <li key={level} className="flex items-center gap-1.5">
                        <span aria-hidden="true" className={`h-2 w-2 rounded-full ${LEVEL_STYLES[level].solid}`} />
                        {counts[level]} {LEVEL_STYLES[level].label.toLowerCase()}
                    </li>
                ))}
                <li>{total - checked} not checked</li>
            </ul>
        </div>
    );
}