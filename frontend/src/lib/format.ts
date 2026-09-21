import { parseServerDate, type StalenessLevel } from "./api";

export interface LevelStyle {
    label: string;
    text: string;
    soft: string;
    solid: string;
    border: string;
    stroke: string;
}

// Class names are written out in full so Tailwind can detect them.
export const LEVEL_STYLES: Record<StalenessLevel, LevelStyle> = {
    fresh: {
        label: "Fresh",
        text: "text-fresh",
        soft: "bg-fresh/15",
        solid: "bg-fresh",
        border: "border-fresh",
        stroke: "stroke-fresh",
    },
    aging: {
        label: "Aging",
        text: "text-aging",
        soft: "bg-aging/15",
        solid: "bg-aging",
        border: "border-aging",
        stroke: "stroke-aging",
    },
    stale: {
        label: "Stale",
        text: "text-stale",
        soft: "bg-stale/15",
        solid: "bg-stale",
        border: "border-stale",
        stroke: "stroke-stale",
    },
    expired: {
        label: "Expired",
        text: "text-expired",
        soft: "bg-expired/15",
        solid: "bg-expired",
        border: "border-expired",
        stroke: "stroke-expired",
    },
};

export function capitalize(value: string): string {
    return value.charAt(0).toUpperCase() + value.slice(1);
}

const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** "just now", "5 minutes ago", "yesterday". `now` is passed in so render stays pure. */
export function formatAge(date: Date, now: number): string {
    const seconds = Math.round((date.getTime() - now) / 1000);
    const abs = Math.abs(seconds);
    if (abs < 45) return "just now";
    if (abs < 3600) return relative.format(Math.round(seconds / 60), "minute");
    if (abs < 86400) return relative.format(Math.round(seconds / 3600), "hour");
    if (abs < 2592000) return relative.format(Math.round(seconds / 86400), "day");
    if (abs < 31536000) return relative.format(Math.round(seconds / 2592000), "month");
    return relative.format(Math.round(seconds / 31536000), "year");
}

export function formatDateTime(date: Date): string {
    return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function describeUse(count: number, lastUsed: string | null, now: number): string {
    if (count === 0) return "Not used yet";
    const times = count === 1 ? "Used once" : `Used ${count} times`;
    return lastUsed ? `${times}, last ${formatAge(parseServerDate(lastUsed), now)}` : times;
}