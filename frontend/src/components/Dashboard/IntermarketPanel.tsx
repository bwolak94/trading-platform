/**
 * IntermarketPanel
 * Displays cross-asset correlation analysis between BTC and DXY, SPX, Gold.
 * Fetches from GET /api/v1/features/intermarket/{symbol}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface IntermarketSignal {
  relationship: string;
  correlation_current: number;
  correlation_baseline: number;
  driver_trend: string;
  expected_impact: string;
  confidence: number;
  description: string;
}

interface IntermarketData {
  symbol: string;
  net_bias: string;
  net_confidence: number;
  risk_regime: string;
  dominant_driver: string;
  signals: IntermarketSignal[];
}

// --------------- Constants ---------------

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

// --------------- Helpers ---------------

function getRiskRegimeStyle(regime: string): { badge: string; label: string } {
  const r = regime.toUpperCase();
  if (r.includes("RISK_ON")) return { badge: "bg-green-500/20 text-green-400", label: "RISK ON" };
  if (r.includes("RISK_OFF")) return { badge: "bg-red-500/20 text-red-400", label: "RISK OFF" };
  return { badge: "bg-gray-700 text-gray-400", label: "MIXED" };
}

function getImpactStyle(impact: string): string {
  const i = impact.toUpperCase();
  if (i.includes("BULL") || i.includes("POSITIVE")) return "text-green-400";
  if (i.includes("BEAR") || i.includes("NEGATIVE")) return "text-red-400";
  return "text-gray-400";
}

function getTrendArrow(trend: string): { arrow: string; color: string } {
  const t = trend.toUpperCase();
  if (t.includes("UP") || t.includes("RISING")) return { arrow: "▲", color: "text-green-400" };
  if (t.includes("DOWN") || t.includes("FALLING")) return { arrow: "▼", color: "text-red-400" };
  return { arrow: "●", color: "text-gray-400" };
}

function getBiasStyle(bias: string): string {
  const b = bias.toUpperCase();
  if (b.includes("BULL")) return "text-green-400";
  if (b.includes("BEAR")) return "text-red-400";
  return "text-gray-400";
}

async function fetchIntermarket(symbol: string): Promise<IntermarketData> {
  const { data } = await axios.get<IntermarketData>(`/api/v1/features/intermarket/${symbol}`);
  return data;
}

// --------------- Correlation Meter ---------------

interface CorrelationMeterProps {
  value: number;  // -1 to +1
  baseline: number;
}

function CorrelationMeter({ value, baseline }: CorrelationMeterProps) {
  // Map -1..+1 to 0..100% width in a centered bar
  const centerPct = 50;
  const valuePct = (value + 1) / 2 * 100;
  const baselinePct = (baseline + 1) / 2 * 100;

  const isPositive = value >= 0;
  const barColor = isPositive ? "bg-green-500" : "bg-red-500";
  const leftPct = Math.min(centerPct, valuePct);
  const widthPct = Math.abs(valuePct - centerPct);

  return (
    <div
      className="relative h-3 w-full overflow-hidden rounded-full bg-gray-700"
      aria-label={`Correlation: ${value.toFixed(2)}, baseline: ${baseline.toFixed(2)}`}
      role="img"
    >
      {/* Center marker */}
      <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gray-500" aria-hidden="true" />
      {/* Filled bar */}
      <div
        className={`absolute top-0 bottom-0 ${barColor} opacity-80 transition-all duration-500`}
        style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
      />
      {/* Baseline marker */}
      <div
        className="absolute top-0 bottom-0 w-0.5 bg-yellow-400/60"
        style={{ left: `${baselinePct}%` }}
        aria-hidden="true"
      />
    </div>
  );
}

// --------------- Signal Row ---------------

interface SignalRowProps {
  signal: IntermarketSignal;
}

function SignalRow({ signal }: SignalRowProps) {
  const trend = getTrendArrow(signal.driver_trend);
  const impactColor = getImpactStyle(signal.expected_impact);

  return (
    <div className="rounded border border-border bg-gray-800/60 px-3 py-2.5 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-200">{signal.relationship}</span>
        <div className="flex items-center gap-2">
          <span className={`text-sm ${trend.color}`} aria-hidden="true">{trend.arrow}</span>
          <span className={`text-xs font-medium ${impactColor}`}>{signal.expected_impact}</span>
          <span className="font-mono text-xs text-gray-500">{signal.confidence.toFixed(0)}%</span>
        </div>
      </div>

      {/* Correlation meter */}
      <div>
        <div className="mb-1 flex items-center justify-between text-[10px] text-gray-500">
          <span>-1.0</span>
          <span>Correlation: <span className="font-mono text-gray-300">{signal.correlation_current.toFixed(2)}</span></span>
          <span>+1.0</span>
        </div>
        <CorrelationMeter value={signal.correlation_current} baseline={signal.correlation_baseline} />
      </div>

      {/* Description */}
      <p className="text-[10px] text-gray-500 italic">{signal.description}</p>
    </div>
  );
}

// --------------- Skeleton ---------------

function IntermarketSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading intermarket data">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-24 animate-pulse rounded bg-white/5" />
      ))}
    </div>
  );
}

// --------------- Main Component ---------------

export default function IntermarketPanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery<IntermarketData>({
    queryKey: ["intermarket", symbol],
    queryFn: () => fetchIntermarket(symbol),
    refetchInterval: 60_000,
    retry: 2,
  });

  const handleRefetch = useCallback(() => { void refetch(); }, [refetch]);
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  const regimeStyle = data ? getRiskRegimeStyle(data.risk_regime) : null;
  const biasColor = data ? getBiasStyle(data.net_bias) : "";

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Intermarket Analysis</h2>
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
            aria-label="Refresh intermarket data"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">Failed to load intermarket data</span>
          <button type="button" onClick={handleRefetch} className="text-xs text-red-400 underline hover:text-red-300">
            Retry
          </button>
        </div>
      )}

      {isLoading && <IntermarketSkeleton />}

      {data && regimeStyle && (
        <div className="space-y-4">
          {/* Risk regime + net bias */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`rounded px-2 py-0.5 text-xs font-bold ${regimeStyle.badge}`}>
                {regimeStyle.label}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <p className="text-[10px] text-gray-500">Net Bias</p>
                <p className={`text-xs font-bold ${biasColor}`}>{data.net_bias}</p>
              </div>
              <div className="text-right">
                <p className="text-[10px] text-gray-500">Confidence</p>
                <p className="font-mono text-xs text-gray-300">{data.net_confidence.toFixed(0)}%</p>
              </div>
            </div>
          </div>

          {/* Dominant driver */}
          {data.dominant_driver && (
            <div className="rounded bg-blue-500/10 border border-blue-500/20 px-3 py-1.5">
              <span className="text-[10px] text-blue-400">Dominant Driver: </span>
              <span className="text-xs text-gray-200 font-medium">{data.dominant_driver}</span>
            </div>
          )}

          {/* Signal rows */}
          <div className="space-y-2">
            {data.signals.map((signal, i) => (
              <SignalRow key={i} signal={signal} />
            ))}
          </div>

          {/* Legend */}
          <div className="flex gap-3 text-[10px] text-gray-500">
            <span className="flex items-center gap-1">
              <span className="inline-block h-1.5 w-4 rounded-full bg-yellow-400/60" aria-hidden="true" />
              Baseline correlation
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
