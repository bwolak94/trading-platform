/**
 * Market Microstructure Score Widget
 * Single-number quality score for current trading conditions
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import axios from "axios";

interface MicrostructureComponent {
  name: string;
  score: number;
  weight: number;
}

interface MicrostructureScoreData {
  symbol: string;
  total_score: number;
  grade: "EXCELLENT" | "GOOD" | "FAIR" | "POOR";
  components: MicrostructureComponent[];
  updated_at: string;
}

interface MicrostructureRaw {
  symbol: string;
  score: number;
  label: string;
  components: Record<string, number>;
  timestamp: string;
}

const COMPONENT_META: { key: string; name: string; max: number; weight: number }[] = [
  { key: "orderbook_imbalance_score", name: "Order Book Quality", max: 25, weight: 0.25 },
  { key: "funding_score", name: "Funding Rate", max: 20, weight: 0.2 },
  { key: "liq_proximity_score", name: "Liquidation Risk", max: 20, weight: 0.2 },
  { key: "cvd_score", name: "CVD Trend", max: 20, weight: 0.2 },
  { key: "volume_score", name: "Volume Confirmation", max: 15, weight: 0.15 },
];

const LABEL_TO_GRADE: Record<string, MicrostructureScoreData["grade"]> = {
  FAVORABLE: "GOOD",
  NEUTRAL: "FAIR",
  AVOID: "POOR",
  EXCELLENT: "EXCELLENT",
  GOOD: "GOOD",
  FAIR: "FAIR",
  POOR: "POOR",
};

async function fetchMicrostructureScore(symbol: string): Promise<MicrostructureScoreData> {
  const { data: raw } = await axios.get<MicrostructureRaw>(
    `/api/v1/market/microstructure-score/${symbol}`,
  );
  const components: MicrostructureComponent[] = COMPONENT_META.map(({ key, name, max, weight }) => ({
    name,
    score: Math.round(((raw.components?.[key] ?? 0) / max) * 100),
    weight,
  }));
  return {
    symbol: raw.symbol,
    total_score: raw.score ?? 0,
    grade: LABEL_TO_GRADE[raw.label] ?? "FAIR",
    components,
    updated_at: raw.timestamp ?? new Date().toISOString(),
  };
}

const DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];

const GRADE_STYLES = {
  EXCELLENT: { color: "text-bullish", stroke: "#22c55e", bg: "bg-bullish/10" },
  GOOD: { color: "text-blue-400", stroke: "#60a5fa", bg: "bg-blue-400/10" },
  FAIR: { color: "text-amber-400", stroke: "#fbbf24", bg: "bg-amber-400/10" },
  POOR: { color: "text-bearish", stroke: "#ef4444", bg: "bg-bearish/10" },
} as const;

function CircularScore({
  score,
  grade,
}: {
  score: number;
  grade: MicrostructureScoreData["grade"];
}) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.min(1, Math.max(0, score / 100));
  const dashOffset = circumference * (1 - progress);
  const styles = GRADE_STYLES[grade];

  return (
    <div className="flex flex-col items-center">
      <div className="relative inline-flex items-center justify-center">
        <svg
          className="h-28 w-28 -rotate-90"
          viewBox="0 0 100 100"
          aria-hidden="true"
        >
          {/* Background track */}
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth="8"
          />
          {/* Progress arc */}
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={styles.stroke}
            strokeWidth="8"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.5s ease" }}
          />
        </svg>
        <div className="absolute flex flex-col items-center">
          <span className={`text-3xl font-bold ${styles.color}`}>
            {Math.round(score)}
          </span>
          <span className="text-xs text-gray-500">/ 100</span>
        </div>
      </div>
      <span
        className={`mt-1 rounded px-2 py-0.5 text-xs font-bold ${styles.color} ${styles.bg}`}
      >
        {grade}
      </span>
    </div>
  );
}

function ComponentBar({ component }: { component: MicrostructureComponent }) {
  const pct = Math.min(100, Math.max(0, component.score));
  const color =
    pct >= 70 ? "bg-bullish" : pct >= 40 ? "bg-amber-400" : "bg-bearish";

  return (
    <div>
      <div className="mb-1 flex justify-between text-[10px]">
        <span className="text-gray-400">{component.name}</span>
        <span className="text-gray-300">{Math.round(pct)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className={`h-full rounded-full ${color} transition-all duration-500`}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={Math.round(pct)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={component.name}
        />
      </div>
    </div>
  );
}

const DEFAULT_COMPONENTS: MicrostructureComponent[] = [
  { name: "Order Book Quality", score: 0, weight: 0.2 },
  { name: "Funding Rate Environment", score: 0, weight: 0.2 },
  { name: "Liquidation Risk", score: 0, weight: 0.2 },
  { name: "Volume Confirmation", score: 0, weight: 0.2 },
  { name: "CVD Trend", score: 0, weight: 0.2 },
];

export function MarketMicrostructureScore() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["microstructure-score", symbol],
    queryFn: () => fetchMicrostructureScore(symbol),
    refetchInterval: 30_000,
    retry: false,
  });

  const components = data?.components ?? DEFAULT_COMPONENTS;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Market Microstructure</h2>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent"
          aria-label="Select asset for microstructure score"
        >
          {DEFAULT_SYMBOLS.map((s) => (
            <option key={s} value={s}>
              {s.replace("USDT", "")}
            </option>
          ))}
        </select>
      </div>

      {isError && (
        <div className="mb-3 rounded bg-bearish/10 px-3 py-2 text-xs text-bearish">
          Score data unavailable
        </div>
      )}

      {isLoading ? (
        <div className="flex flex-col items-center gap-4">
          <div className="h-28 w-28 animate-pulse rounded-full bg-white/5" />
          <div className="w-full space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="space-y-1">
                <div className="h-2 w-32 animate-pulse rounded bg-white/5" />
                <div className="h-1.5 w-full animate-pulse rounded-full bg-white/5" />
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex justify-center">
            <CircularScore
              score={data?.total_score ?? 0}
              grade={data?.grade ?? "POOR"}
            />
          </div>
          <div className="space-y-2">
            {components.map((comp) => (
              <ComponentBar key={comp.name} component={comp} />
            ))}
          </div>
          {data?.updated_at && (
            <p className="text-center text-[10px] text-gray-600">
              Updated: {new Date(data.updated_at).toLocaleTimeString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
