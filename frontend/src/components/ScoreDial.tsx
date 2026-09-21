import type { CSSProperties } from "react";
import type { StalenessLevel } from "@/lib/api";
import { LEVEL_STYLES } from "@/lib/format";

const RADIUS = 42;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

interface Props {
  score: number;
  level: StalenessLevel;
  /** The contradiction check failed, so the score is partial and its level can't be trusted. */
  incomplete?: boolean;
}

/**
 * A clock face: twelve ticks around a ring that sweeps clockwise from
 * twelve o'clock in proportion to the final score. The ring takes the
 * color of the staleness level, unless the check was incomplete, in which
 * case it stays neutral and says so.
 */
export function ScoreDial({ score, level, incomplete = false }: Props) {
  const style = LEVEL_STYLES[level];
  const label = incomplete ? "Incomplete" : style.label;
  const labelClass = incomplete ? "text-aging" : style.text;
  const arcClass = incomplete ? "stroke-muted" : style.stroke;
  const clamped = Math.min(Math.max(score, 0), 1);
  const offset = CIRCUMFERENCE * (1 - clamped);

  return (
    <div className="relative h-[120px] w-[120px] shrink-0">
      <svg
        viewBox="0 0 120 120"
        className="h-full w-full"
        role="img"
        aria-label={
          incomplete
            ? `Partial staleness score ${score.toFixed(3)} out of 1; the contradiction check did not complete`
            : `Staleness score ${score.toFixed(3)} out of 1, ${label.toLowerCase()}`
        }
      >
        {Array.from({ length: 12 }, (_, i) => (
          <line
            key={i}
            x1="60"
            y1="6"
            x2="60"
            y2={i % 3 === 0 ? 14 : 11}
            transform={`rotate(${i * 30} 60 60)`}
            className="stroke-muted"
            strokeWidth={i % 3 === 0 ? 2 : 1}
            strokeLinecap="round"
          />
        ))}
        <circle cx="60" cy="60" r={RADIUS} fill="none" strokeWidth="8" className="stroke-rule" />
        {clamped > 0.005 && (
          <circle
            cx="60"
            cy="60"
            r={RADIUS}
            fill="none"
            strokeWidth="8"
            strokeLinecap="round"
            transform="rotate(-90 60 60)"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
            className={`dial-arc ${arcClass}`}
            style={{ "--dial-circ": CIRCUMFERENCE } as CSSProperties}
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-serif text-2xl leading-none tabular-nums">{score.toFixed(3)}</span>
        <span className={`mt-1 text-xs font-medium ${labelClass}`}>{label}</span>
      </div>
    </div>
  );
}