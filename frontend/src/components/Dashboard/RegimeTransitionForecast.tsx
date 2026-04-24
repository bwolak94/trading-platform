/**
 * Regime Transition Probability Forecast
 * Shows probability of regime change in next 4h and 24h
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import axios from "axios";
import type { MarketRegime } from "../../types";

interface RegimeProbability {
  regime: MarketRegime;
  probability: number;
}

interface TransitionForecast {
  symbol: string;
  current_regime: MarketRegime;
  current_confidence: number;
  forecast_4h: RegimeProbability[];
  forecast_24h: RegimeProbability[];
  most_likely_next_4h: MarketRegime;
  most_likely_next_24h: MarketRegime;
  updated_at: string;
}

interface TransitionForecastRaw {
  symbol: string;
  current_regime: string;
  next_4h: Record<string, number>;
  next_24h: Record<string, number>;
  most_likely_next: string;
  change_probability_4h: number;
  regime_duration_hours?: number;
}

function objToArray(obj: Record<string, number>): RegimeProbability[] {
  return Object.entries(obj ?? {}).map(([regime, probability]) => ({
    regime: regime as MarketRegime,
    probability,
  }));
}

async function fetchTransitionForecast(symbol: string): Promise<TransitionForecast> {
  const { data: raw } = await axios.get<TransitionForecastRaw>(
    `/api/v1/regime/transition-forecast/${symbol}`,
  );
  const arr24h = objToArray(raw.next_24h);
  const mostLikely24h = arr24h.sort((a, b) => b.probability - a.probability)[0]?.regime ?? (raw.most_likely_next as MarketRegime);
  return {
    symbol: raw.symbol,
    current_regime: raw.current_regime as MarketRegime,
    current_confidence: 1 - (raw.change_probability_4h ?? 0),
    forecast_4h: objToArray(raw.next_4h),
    forecast_24h: objToArray(raw.next_24h),
    most_likely_next_4h: raw.most_likely_next as MarketRegime,
    most_likely_next_24h: mostLikely24h,
    updated_at: new Date().toISOString(),
  };
}

const REGIME_STYLES: Record<MarketRegime, { label: string; color: string; bg: string }> = {
  TREND_BULL: { label: "Trend Bull", color: "text-bullish", bg: "bg-bullish" },
  TREND_BEAR: { label: "Trend Bear", color: "text-bearish", bg: "bg-bearish" },
  CONSOLIDATION: { label: "Consolidation", color: "text-gray-400", bg: "bg-gray-500" },
  HIGH_VOL_CHOPPY: { label: "High Vol Choppy", color: "text-amber-400", bg: "bg-amber-400" },
};

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];

function ProbabilityBar({
  regime,
  probability,
}: {
  regime: MarketRegime;
  probability: number;
}) {
  const styles = REGIME_STYLES[regime];
  const pct = Math.round(probability * 100);

  return (
    <div>
      <div className="mb-0.5 flex justify-between text-[10px]">
        <span className={styles.color}>{styles.label}</span>
        <span className="text-gray-300">{pct}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className={`h-full rounded-full ${styles.bg} transition-all duration-500`}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${styles.label}: ${pct}%`}
        />
      </div>
    </div>
  );
}

function ForecastSection({
  label,
  probabilities,
  mostLikely,
}: {
  label: string;
  probabilities: RegimeProbability[];
  mostLikely: MarketRegime;
}) {
  const styles = REGIME_STYLES[mostLikely];
  const sorted = [...probabilities].sort((a, b) => b.probability - a.probability);

  return (
    <div className="rounded border border-border/40 bg-surface/50 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium text-gray-400">{label}</span>
        <span className={`text-xs font-semibold ${styles.color}`}>
          {styles.label} ({Math.round((sorted[0]?.probability ?? 0) * 100)}%)
        </span>
      </div>
      <div className="space-y-1.5">
        {sorted.map((p) => (
          <ProbabilityBar key={p.regime} regime={p.regime} probability={p.probability} />
        ))}
      </div>
    </div>
  );
}

function SkeletonSection() {
  return (
    <div className="rounded border border-border/40 p-3 space-y-2">
      <div className="h-3 w-24 animate-pulse rounded bg-white/5" />
      {[...Array(4)].map((_, i) => (
        <div key={i} className="space-y-1">
          <div className="h-2 w-full animate-pulse rounded bg-white/5" />
          <div className="h-1.5 w-full animate-pulse rounded-full bg-white/5" />
        </div>
      ))}
    </div>
  );
}

export function RegimeTransitionForecast() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["regime-transition-forecast", symbol],
    queryFn: () => fetchTransitionForecast(symbol),
    refetchInterval: 60_000,
    retry: false,
  });

  const currentStyles = data
    ? REGIME_STYLES[data.current_regime]
    : null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Regime Transition Forecast</h2>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent"
          aria-label="Select asset for regime forecast"
        >
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>
              {s.replace("USDT", "")}
            </option>
          ))}
        </select>
      </div>

      {isError && (
        <div className="mb-3 rounded bg-bearish/10 px-3 py-2 text-xs text-bearish">
          Forecast unavailable
        </div>
      )}

      {/* Current regime */}
      {!isLoading && data && currentStyles && (
        <div className="mb-4 flex items-center justify-between rounded border border-border/50 bg-surface/50 px-3 py-2">
          <span className="text-xs text-gray-500">Current Regime</span>
          <div className="flex items-center gap-2">
            <span className={`text-sm font-bold ${currentStyles.color}`}>
              {currentStyles.label}
            </span>
            <span className="text-xs text-gray-500">
              {Math.round(data.current_confidence * 100)}% conf.
            </span>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <SkeletonSection />
          <SkeletonSection />
        </div>
      ) : (
        data && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <ForecastSection
              label="Next 4h"
              probabilities={data.forecast_4h}
              mostLikely={data.most_likely_next_4h}
            />
            <ForecastSection
              label="Next 24h"
              probabilities={data.forecast_24h}
              mostLikely={data.most_likely_next_24h}
            />
          </div>
        )
      )}
    </div>
  );
}
