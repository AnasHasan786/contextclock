// Shared class strings for form controls, so the page and the entries match.

export const labelClass = "mb-1.5 block text-sm font-medium";

export const inputClass =
  "w-full rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink placeholder:text-muted/70";

// Primary actions invert ink and paper, so the only colors on the page are
// the staleness levels.
export const primaryButton =
  "inline-flex items-center justify-center rounded-full bg-ink px-4 py-2 text-sm font-medium text-paper transition-opacity hover:opacity-85 cursor-pointer disabled:cursor-not-allowed disabled:opacity-40";

export const ghostButton =
  "inline-flex items-center justify-center rounded-full border border-rule px-4 py-2 text-sm font-medium transition-colors hover:border-muted cursor-pointer disabled:cursor-not-allowed disabled:opacity-40";