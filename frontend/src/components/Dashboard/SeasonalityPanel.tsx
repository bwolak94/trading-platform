/**
 * SeasonalityPanel
 * Displays historical seasonality patterns by hour and day of week.
 * Fetches from GET /api/v1/features/seasonality/{symbol}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface SeasonalityPeriod {
  period_label: string;
  win_rate: number;
  avg_return_pct: number;
  trade_count: number;
}

interface SeasonalityData {
  symbol: string;
  best_hours: SeasonalityPeriod[];
  worst_hours: SeasonalityPeriod[];
  best_days: SeasonalityPeriod[];
  worst_days: SeasonalityPeriod[];
  current_period_multiplier: number;
  recommendation: string;
}

type ViewTab = "hours" | "days";

// --------------- Constants ---------------

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];

const HOURS_24 = Array.from({ length: 24 }, (_, i) => i);
const DAYS_7 = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// --------------- Helpers ---------------

function getWinRateColor(wr: number): string {
  if (wr >= 0.6) return "bg-green-500";
  if (wr >= 0.45) return "bg-yellow-500";
  return "bg-red-500";
}

function getWinRateTextColor(wr: number): string {
  if (wr >= 0.6) return "text-green-400";
  if (wr >= 0.45) return "text-yellow-400";
  return "text-red-400";
}

function getReturnColor(ret: number): string {
  if (ret > 0) return "text-green-400";
  if (ret < 0) return "text-red-400";
  return "text-gray-400";
}

function getMultiplierStyle(mult: number): { text: string; badge: string } {
  if (mult >= 1.3) return { text: "text-green-400", badge: "bg-green-500/20 text-green-400" };
  if (mult >= 0.8) return { text: "text-yellow-400", badge: "bg-yellow-500/20 text-yellow-400" };
  return { text: "text-red-400", badge: "bg-red-500/20 text-red-400" };
}

async function fetchSeasonality(symbol: string): Promise<SeasonalityData> {
  const { data } = await axios.get<SeasonalityData>(`/api/v1/features/seasonality/${symbol}`);
  return data;
}

// --------------- Hour Heatmap ---------------

interface HourHeatmapProps {
  bestHours: SeasonalityPeriod[];
  worstHours: SeasonalityPeriod[];
  currentHour: number;
}

function HourHeatmap({ bestHours, worstHours, currentHour }: HourHeatmapProps) {
  // Build a map from hour -> win_rate
  const hourMap = new Map<number, number>();
  for (const h of bestHours) {
    const hourNum = parseInt(h.period_label.replace("H", "").replace(":00", ""), 10);
    if (!isNaN(hourNum)) hourMap.set(hourNum, h.win_rate);
  }
  for (const h of worstHours) {
    const hourNum = parseInt(h.period_label.replace("H", "").replace(":00", ""), 10);
    if (!isNaN(hourNum)) hourMap.set(hourNum, h.win_rate);
  }

  return (
    <div
      className="grid grid-cols-12 gap-0.5"
      aria-label="24-hour win rate heatmap"
      role="img"
    >
      {HOURS_24.map((h) => {
        const wr = hourMap.get(h) ?? 0.5;
        const isCurrentHour = h === currentHour;
        const bgColor = getWinRateColor(wr);
        const label = `Hour ${h}: ${(wr * 100).toFixed(0)}% win rate`;

        return (
          <div
            key={h}
            className={`relative flex flex-col items-center rounded-sm ${isCurrentHour ? "ring-1 ring-white ring-offset-1 ring-offset-gray-900" : ""}`}
            title={label}
            aria-label={label}
          >
            <div
              className={`h-7 w-full rounded-sm opacity-80 ${bgColor} ${isCurrentHour ? "opacity-100" : ""}`}
            />
            <span className="mt-0.5 text-[8px] text-gray-600">{h}</span>
          </div>
        );
      })}
    </div>
  );
}

// --------------- Day Bar Chart ---------------

interface DayBarsProps {
  bestDays: SeasonalityPeriod[];
  worstDays: SeasonalityPeriod[];
  currentDay: number;
}

function DayBars({ bestDays, worstDays, currentDay }: DayBarsProps) {
  const dayMap = new Map<string, SeasonalityPeriod>();
  for (const d of bestDays) dayMap.set(d.period_label, d);
  for (const d of worstDays) dayMap.set(d.period_label, d);

  const allData = DAYS_7.map((day, i) => {
    const period = dayMap.get(day) ?? dayMap.get(`DAY_${i}`) ?? { period_label: day, win_rate: 0.5, avg_return_pct: 0, trade_count: 0 };
    return { day, isCurrentDay: i === currentDay, ...period };
  });

  const maxWR = Math.max(...allData.map((d) => d.win_rate), 0.01);

  return (
    <div className="flex items-end gap-1 h-24" aria-label="Day of week win rate chart" role="img">
      {allData.map(({ day, win_rate, avg_return_pct, isCurrentDay }) => {
        const heightPct = (win_rate / maxWR) * 80;
        const barColor = getWinRateColor(win_rate);
        const retColor = getReturnColor(avg_return_pct);

        return (
          <div
            key={day}
            className="flex flex-1 flex-col items-center gap-0.5"
            title={`${day}: ${(win_rate * 100).toFixed(0)}% WR, ${avg_return_pct > 0 ? "+" : ""}${avg_return_pct.toFixed(2)}% avg`}
          >
            <span className={`text-[9px] ${retColor}`}>
              {avg_return_pct > 0 ? "+" : ""}{avg_return_pct.toFixed(1)}%
            </span>
            <div className="flex w-full flex-col justify-end" style={{ height: "60px" }}>
              <div
                className={`w-full rounded-t transition-all ${barColor} ${isCurrentDay ? "ring-1 ring-white" : "opacity-70"}`}
                style={{ height: `${heightPct}%` }}
                aria-hidden="true"
              />
            </div>
            <span className={`text-[9px] ${isCurrentDay ? "text-white font-bold" : "text-gray-500"}`}>
              {day}
            </span>
            <span className={`text-[8px] font-mono ${getWinRateTextColor(win_rate)}`}>
              {(win_rate * 100).toFixed(0)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

// --------------- Skeleton ---------------

function SeasonalitySkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading seasonality data">
      <div className="h-8 animate-pulse rounded bg-white/5" />
      <div className="h-24 animate-pulse rounded bg-white/5" />
      {[...Array(2)].map((_, i) => (
        <div key={i} className="h-4 animate-pulse rounded bg-white/5" />
      ))}
    </div>
  );
}

// --------------- Main Component ---------------

export default function SeasonalityPanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [activeTab, setActiveTab] = useState<ViewTab>("hours");

  const now = new Date();
  const currentHour = now.getHours();
  const currentDay = now.getDay();

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery<SeasonalityData>({
    queryKey: ["seasonality", symbol],
    queryFn: () => fetchSeasonality(symbol),
    refetchInterval: 5 * 60_000,
    retry: 2,
  });

  const handleRefetch = useCallback(() => { void refetch(); }, [refetch]);
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  const multiplierStyle = data ? getMultiplierStyle(data.current_period_multiplier) : null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Seasonality</h2>
          {lastUpdated && (
            <p className="mt-0.5 text-xs text-gray-500">Updated: {lastUpdated}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <select
            value={symbol}
            onChange={(e) => { setSymbol(e.target.value); }}
            className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-label="Select symbol"
          >
            {SYMBOLS.map((s) => (
              <option key={s} value={s}>{s.replace("USDT", "")}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={handleRefetch}
            className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-400 hover:text-white transition-colors"
            aria-label="Refresh seasonality data"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load seasonality data</span>
          <button type="button" onClick={handleRefetch} className="text-xs text-red-400 underline hover:text-red-300">
            Retry
          </button>
        </div>
      )}

      {isLoading && <SeasonalitySkeleton />}

      {data && multiplierStyle && (
        <div className="space-y-4">
          {/* Current period stats */}
          <div className="flex items-center justify-between rounded bg-gray-800/60 border border-border px-3 py-2">
            <div>
              <p className="text-[10px] text-gray-500">Current Period Multiplier</p>
              <p className={`font-mono text-xl font-bold ${multiplierStyle.text}`}>
                {data.current_period_multiplier.toFixed(2)}x
              </p>
            </div>
            <div className="text-right">
              <span className={`rounded px-2 py-0.5 text-xs font-bold ${multiplierStyle.badge}`}>
                {data.current_period_multiplier >= 1.3
                  ? "FAVORABLE"
                  : data.current_period_multiplier >= 0.8
                  ? "NEUTRAL"
                  : "UNFAVORABLE"}
              </span>
              <p className="mt-1 text-[10px] text-gray-500">
                {DAYS_7[currentDay]}, {currentHour.toString().padStart(2, "0")}:00 UTC
              </p>
            </div>
          </div>

          {/* Tab switcher */}
          <div className="flex rounded-lg border border-border bg-gray-800/40 p-0.5" role="tablist">
            {(["hours", "days"] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={activeTab === tab}
                onClick={() => { setActiveTab(tab); }}
                className={`flex-1 rounded-md py-1.5 text-xs font-medium transition-colors ${
                  activeTab === tab
                    ? "bg-gray-700 text-white"
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                {tab === "hours" ? "By Hour" : "By Day"}
              </button>
            ))}
          </div>

          {/* Heatmap / bars */}
          <div>
            {activeTab === "hours" && (
              <div>
                <HourHeatmap
                  bestHours={data.best_hours}
                  worstHours={data.worst_hours}
                  currentHour={currentHour}
                />
                <div className="mt-2 flex gap-4 text-[10px] text-gray-500">
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-sm bg-green-500" aria-hidden="true" /> &gt;60% WR
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-sm bg-yellow-500" aria-hidden="true" /> 45-60%
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-sm bg-red-500" aria-hidden="true" /> &lt;45%
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-sm bg-white" aria-hidden="true" /> Current
                  </span>
                </div>
              </div>
            )}

            {activeTab === "days" && (
              <DayBars
                bestDays={data.best_days}
                worstDays={data.worst_days}
                currentDay={currentDay}
              />
            )}
          </div>

          {/* Recommendation */}
          <div className="rounded bg-gray-800/60 border border-border px-3 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 mb-0.5">
              Recommendation
            </p>
            <p className={`text-xs font-medium ${multiplierStyle.text}`}>{data.recommendation}</p>
          </div>
        </div>
      )}
    </div>
  );
}
