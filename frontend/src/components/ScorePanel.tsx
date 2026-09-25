import { isCheckIncomplete, parseServerDate, type StalenessScore } from "@/lib/api";
import { formatAge } from "@/lib/format";
import { ScoreDial } from "./ScoreDial";

interface Signal {
    label: string;
    hint: string;
    value: number;
    alert: boolean;
    /** No value to show: the signal could not be computed. */
    unavailable?: boolean;
}

function SignalRow({ signal }: { signal: Signal }) {
    const percent = Math.round(Math.min(Math.max(signal.value, 0), 1) * 100);
    return (
        <li>
            <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-medium" title={signal.hint}>
                    {signal.label}
                </span>
                {signal.unavailable ? (
                    <span className="text-sm text-aging">Unavailable</span>
                ) : (
                    <span className="text-sm tabular-nums text-muted">{signal.value.toFixed(2)}</span>
                )}
            </div>
            {signal.unavailable ? (
                <div className="mt-1.5 h-1.5 rounded-full border border-dashed border-aging/60" />
            ) : (
                <div
                    role="meter"
                    aria-label={signal.label}
                    aria-valuemin={0}
                    aria-valuemax={1}
                    aria-valuenow={signal.value}
                    className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-rule"
                >
                    <div
                        className={`bar-fill h-full rounded-full ${signal.alert ? "bg-expired" : "bg-ink/60"}`}
                        style={{ width: `${percent}%` }}
                    />
                </div>
            )}
            <p className="sr-only">{signal.hint}</p>
        </li>
    );
}

export function ScorePanel({ score, now }: { score: StalenessScore; now: number }) {
    const incomplete = isCheckIncomplete(score);
    const contradicted = !incomplete && score.contradiction_score > 0;

    const signals: Signal[] = [
        {
            label: "Time decay",
            hint: "Based on its age and its category's half-life.",
            value: score.time_decay_score,
            alert: false,
        },
        {
            label: "Contradiction",
            hint: incomplete
                ? "The comparison failed, so this signal is missing."
                : "Checked against newer memories in this scope.",
            value: score.contradiction_score,
            alert: contradicted,
            unavailable: incomplete,
        },
        {
            label: "Access anomaly",
            hint: "Based on how often and how recently it was used, relative to its age.",
            value: score.access_anomaly_score,
            alert: false,
        },
    ];

    // The backend joins its reasoning with " | "; show each part on its own line.
    const explanation = score.explanation.split(" | ").filter((part) => part.trim() !== "");

    return (
        <section
            aria-label="Staleness result"
            className="mt-4 rounded-2xl border border-rule bg-surface p-5"
        >
            <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
                <ScoreDial
                    score={score.final_score}
                    level={score.staleness_level}
                    incomplete={incomplete}
                />
                <ul className="min-w-0 flex-1 space-y-3.5">
                    {signals.map((signal) => (
                        <SignalRow key={signal.label} signal={signal} />
                    ))}
                </ul>
            </div>

            {incomplete && (
                <p role="status" className="mt-5 rounded-lg bg-aging/10 px-3 py-2 text-sm text-aging">
                    Couldn&apos;t finish comparing this memory with newer ones, so the score above is
                    partial and could be too low. Gemini may be busy or unreachable. Try again in a minute.
                </p>
            )}

            {contradicted && (
                <p className="mt-5 rounded-lg bg-expired/10 px-3 py-2 text-sm text-expired">
                    A newer memory contradicts or replaces this one.
                </p>
            )}

            <details className="mt-5 border-t border-rule pt-4">
                <summary className="cursor-pointer text-sm font-medium">How this was calculated</summary>
                <ul className="mt-3 space-y-2 text-sm text-muted">
                    {explanation.map((part, index) => (
                        <li key={index}>{part}</li>
                    ))}
                </ul>
            </details>

            <p className="mt-4 text-xs text-muted">
                Checked {formatAge(parseServerDate(score.computed_at), now)}
            </p>
        </section>
    );
}