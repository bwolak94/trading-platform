/**
 * Unified number formatting utilities.
 * Single source of truth for all currency, percentage, and numeric display.
 */

/** Format a USD price with appropriate decimal precision. */
export function fmtPrice(value: number | null | undefined): string {
  if (value == null || !isFinite(value)) return "—";
  if (value >= 1_000) {
    return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (value >= 1) {
    return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
  }
  return `$${value.toPrecision(4)}`;
}

/** Format a dollar amount with compact notation for large values. */
export function fmtUSD(value: number | null | undefined, decimals = 2): string {
  if (value == null || !isFinite(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000_000) return `${sign}$${(abs / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(decimals)}`;
}

/** Format a percentage with sign prefix and configurable decimals. */
export function fmtPct(
  value: number | null | undefined,
  opts: { decimals?: number; showSign?: boolean } = {},
): string {
  if (value == null || !isFinite(value)) return "—";
  const { decimals = 2, showSign = false } = opts;
  const sign = showSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(decimals)}%`;
}

/** Format a plain number with optional compact notation. */
export function fmtNumber(
  value: number | null | undefined,
  opts: { decimals?: number; compact?: boolean } = {},
): string {
  if (value == null || !isFinite(value)) return "—";
  const { decimals = 2, compact = false } = opts;
  if (compact) {
    const abs = Math.abs(value);
    const sign = value < 0 ? "-" : "";
    if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(1)}M`;
    if (abs >= 1_000) return `${sign}${(abs / 1_000).toFixed(1)}K`;
  }
  return value.toFixed(decimals);
}

/** Format a ratio (e.g. 1.5x, 2.3x). */
export function fmtRatio(value: number | null | undefined, decimals = 1): string {
  if (value == null || !isFinite(value)) return "—";
  return `${value.toFixed(decimals)}x`;
}

/** Format a sharpe/sortino ratio. */
export function fmtSharpe(value: number | null | undefined): string {
  if (value == null || !isFinite(value)) return "—";
  return value.toFixed(2);
}

/** CSS class for a positive/negative value. */
export function colorClass(
  value: number | null | undefined,
  neutralClass = "text-gray-400",
): string {
  if (value == null) return neutralClass;
  if (value > 0) return "text-bullish";
  if (value < 0) return "text-bearish";
  return neutralClass;
}

/** Format a date string to locale time. */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** Format a date string to locale date+time. */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
