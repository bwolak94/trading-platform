import { useQuery } from "@tanstack/react-query";
import { fetchMacroData } from "../../api/client";
import type { MacroData } from "../../api/client";

/* ── Helpers ──────────────────────────────────────────────────────── */

function formatChange(value: number | null, suffix = "%"): string {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}${suffix}`;
}

function changeBadgeClass(value: number | null, invert = false): string {
  if (value === null) return "text-gray-400";
  const positive = value > 0;
  const isGreen = invert ? !positive : positive;
  return isGreen ? "text-bullish" : "text-bearish";
}

function correlationLabel(corr: number | null): string {
  if (corr === null) return "N/A";
  if (corr < -0.5) return "Strong Negative";
  if (corr < -0.2) return "Weak Negative";
  if (corr < 0.2) return "Neutral";
  if (corr < 0.5) return "Weak Positive";
  return "Strong Positive";
}

function correlationBadgeClass(corr: number | null): string {
  if (corr === null) return "bg-gray-700 text-gray-300";
  // Negative BTC/DXY correlation is healthy (DXY down = crypto up)
  if (corr < -0.3) return "bg-bullish/20 text-bullish border border-bullish/30";
  if (corr > 0.3) return "bg-bearish/20 text-bearish border border-bearish/30";
  return "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30";
}

/* ── Sub-components ───────────────────────────────────────────────── */

interface MetricCardProps {
  label: string;
  price: number | null;
  changePct: number | null;
  priceDecimals?: number;
  /** When true, a positive change is bearish (e.g. DXY up = crypto headwind) */
  invertSentiment?: boolean;
  suffix?: string;
  pricePrefix?: string;
}

function MetricCard({
  label,
  price,
  changePct,
  priceDecimals = 2,
  invertSentiment = false,
  suffix = "%",
  pricePrefix = "",
}: MetricCardProps) {
  const changeClass = changeBadgeClass(changePct, invertSentiment);
  const changeText = formatChange(changePct, suffix);

  return (
    <div className="rounded-lg border border-border bg-surface p-3 flex flex-col gap-1">
      <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">{label}</span>
      <span className="text-sm font-bold text-white">
        {price !== null ? `${pricePrefix}${price.toFixed(priceDecimals)}` : "—"}
      </span>
      <span className={`text-xs font-medium ${changeClass}`} aria-label={`${label} change: ${changeText}`}>
        {changeText}
      </span>
    </div>
  );
}

/* ── MacroPanel ───────────────────────────────────────────────────── */

interface MacroPanelProps {
  /** Override refetch interval in milliseconds. Defaults to 60 minutes. */
  refetchIntervalMs?: number;
}

export function MacroPanel({ refetchIntervalMs = 60 * 60 * 1000 }: MacroPanelProps) {
  const { data, isLoading, isError, dataUpdatedAt } = useQuery<MacroData>({
    queryKey: ["macroData"],
    queryFn: fetchMacroData,
    refetchInterval: refetchIntervalMs,
    staleTime: 55 * 60 * 1000, // consider fresh for 55 min
  });

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <section
      aria-label="Macro Market Overlay"
      className="rounded-xl border border-border bg-background p-4 space-y-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white uppercase tracking-wide">
          Macro Overlay
        </h2>
        {isLoading && (
          <span className="text-xs text-gray-500 animate-pulse">Loading...</span>
        )}
        {isError && (
          <span className="text-xs text-bearish">Data unavailable</span>
        )}
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard
          label="DXY"
          price={data?.dxy_price ?? null}
          changePct={data?.dxy_change_pct ?? null}
          priceDecimals={2}
          invertSentiment
        />
        <MetricCard
          label="US 10Y Yield"
          price={data?.us10y_yield ?? null}
          changePct={data?.us10y_change_pct ?? null}
          priceDecimals={3}
          suffix="%"
          invertSentiment
        />
        <MetricCard
          label="S&P 500"
          price={data?.spx_price ?? null}
          changePct={data?.spx_change_pct ?? null}
          priceDecimals={2}
          pricePrefix=""
        />
        {/* BTC/DXY Correlation badge as a special card */}
        <div className="rounded-lg border border-border bg-surface p-3 flex flex-col gap-1">
          <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">
            BTC/DXY Corr.
          </span>
          <span className="text-sm font-bold text-white">
            {data?.btc_correlation_dxy !== null && data?.btc_correlation_dxy !== undefined
              ? data.btc_correlation_dxy.toFixed(3)
              : "—"}
          </span>
          <span
            className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium w-fit ${correlationBadgeClass(data?.btc_correlation_dxy ?? null)}`}
            aria-label={`BTC/DXY correlation: ${correlationLabel(data?.btc_correlation_dxy ?? null)}`}
          >
            {correlationLabel(data?.btc_correlation_dxy ?? null)}
          </span>
        </div>
      </div>

      {/* DXY Interpretation hint */}
      {data?.dxy_change_pct !== null && data?.dxy_change_pct !== undefined && (
        <div
          className={`rounded border px-3 py-2 text-xs ${
            data.dxy_change_pct > 0
              ? "border-bearish/30 bg-bearish/5 text-bearish"
              : "border-bullish/30 bg-bullish/5 text-bullish"
          }`}
          role="status"
          aria-live="polite"
        >
          {data.dxy_change_pct > 0
            ? "DXY rising — potential crypto headwind. Monitor risk exposure."
            : "DXY falling — historically supportive for risk assets and crypto."}
        </div>
      )}

      {/* Footer */}
      <p className="text-xs text-gray-600">
        Data via Yahoo Finance · Updated hourly
        {lastUpdated && <span className="ml-1">(last: {lastUpdated})</span>}
      </p>
    </section>
  );
}
