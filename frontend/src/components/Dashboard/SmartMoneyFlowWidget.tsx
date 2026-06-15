/**
 * SmartMoneyFlowWidget
 * Shows institutional vs retail flow bias with signal badge.
 * Fetches from GET /api/v1/features2/smart-money-flow/{symbol}
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// --------------- Types ---------------

interface SmartMoneyData {
  signal: string;
  bias: number;
  institutional_buy_ratio: number;
  retail_buy_ratio: number;
  confidence: number;
  description: string;
}

// --------------- Constants ---------------

type SignalType =
  | "INSTITUTIONAL_ACCUMULATION"
  | "RETAIL_FOMO"
  | "SMART_DISTRIBUTION"
  | "NEUTRAL";

const SIGNAL_CONFIG: Record<
  SignalType,
  { label: string; badge: string; border: string; bg: string }
> = {
  INSTITUTIONAL_ACCUMULATION: {
    label: "Smart money accumulating",
    badge: "bg-green-500/20 text-green-400 border border-green-500/40",
    border: "border-green-500/30",
    bg: "bg-green-500/5",
  },
  RETAIL_FOMO: {
    label: "Retail FOMO — potential fade",
    badge: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/40",
    border: "border-yellow-500/30",
    bg: "bg-yellow-500/5",
  },
  SMART_DISTRIBUTION: {
    label: "Smart money distributing",
    badge: "bg-red-500/20 text-red-400 border border-red-500/40",
    border: "border-red-500/30",
    bg: "bg-red-500/5",
  },
  NEUTRAL: {
    label: "No clear bias",
    badge: "bg-gray-700 text-gray-400 border border-gray-600",
    border: "border-gray-700",
    bg: "bg-gray-800/40",
  },
};

const SYMBOL_OPTIONS = [
  "BTCUSDT",
  "ETHUSDT",
  "SOLUSDT",
  "BNBUSDT",
  "XRPUSDT",
  "ADAUSDT",
];

// --------------- Fetch helper ---------------

async function fetchSmartMoneyFlow(symbol: string): Promise<SmartMoneyData> {
  const { data } = await axios.get<SmartMoneyData>(
    `/api/v1/features2/smart-money-flow/${symbol}`,
  );
  return data;
}

// --------------- Sub-component: Bias Gauge ---------------

function BiasGauge({ bias }: { bias: number }) {
  // bias is -1 (max sell) to +1 (max buy)
  const clamped = Math.max(-1, Math.min(1, bias));
  const pct = (clamped + 1) / 2; // 0–1 for bar position
  const cx = 80;
  const r = 60;

  const angle = Math.PI - pct * Math.PI; // PI (left) to 0 (right)
  const x = cx + r * Math.cos(angle);
  const y = 70 + r * Math.sin(angle);

  const color =
    clamped > 0.3 ? "#22c55e" : clamped < -0.3 ? "#ef4444" : "#6b7280";

  return (
    <div className="flex flex-col items-center">
      <svg
        viewBox="0 0 160 80"
        className="w-36"
        aria-label={`Smart money bias: ${(clamped * 100).toFixed(0)}%`}
        role="img"
      >
        {/* Background arc */}
        <path
          d="M 20 70 A 60 60 0 0 1 140 70"
          fill="none"
          stroke="rgba(255,255,255,0.05)"
          strokeWidth="10"
          strokeLinecap="round"
        />
        {/* Color zones */}
        <path
          d="M 20 70 A 60 60 0 0 1 80 10"
          fill="none"
          stroke="rgba(239,68,68,0.3)"
          strokeWidth="10"
          strokeLinecap="round"
        />
        <path
          d="M 80 10 A 60 60 0 0 1 140 70"
          fill="none"
          stroke="rgba(34,197,94,0.3)"
          strokeWidth="10"
          strokeLinecap="round"
        />
        {/* Needle */}
        <line
          x1={cx}
          y1={70}
          x2={x}
          y2={y}
          stroke={color}
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        <circle cx={cx} cy={70} r="4" fill={color} />
        {/* Labels */}
        <text x="14" y="82" fontSize="9" fill="#6b7280">
          SELL
        </text>
        <text x="114" y="82" fontSize="9" fill="#6b7280">
          BUY
        </text>
      </svg>
      <p
        className={`font-mono text-xl font-bold ${
          clamped > 0.3
            ? "text-green-400"
            : clamped < -0.3
              ? "text-red-400"
              : "text-gray-400"
        }`}
      >
        {clamped > 0 ? "+" : ""}
        {(clamped * 100).toFixed(0)}
      </p>
      <p className="text-[10px] text-gray-500">bias score</p>
    </div>
  );
}

// --------------- Sub-component: Flow Bar ---------------

function FlowBar({
  label,
  ratio,
  color,
}: {
  label: string;
  ratio: number;
  color: string;
}) {
  const pct = Math.min(Math.max(ratio, 0), 1) * 100;
  return (
    <div>
      <div className="mb-1 flex justify-between text-[10px]">
        <span className="text-gray-400">{label}</span>
        <span
          className={`font-mono font-semibold ${color}`}
        >
          {pct.toFixed(1)}% buy
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-700">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            ratio >= 0.6
              ? "bg-green-500"
              : ratio <= 0.4
                ? "bg-red-500"
                : "bg-yellow-500"
          }`}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${label}: ${pct.toFixed(1)}% buy`}
        />
      </div>
    </div>
  );
}

// --------------- Skeleton ---------------

function SmartMoneySkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading smart money data">
      <div className="flex justify-center">
        <div className="h-20 w-36 animate-pulse rounded bg-white/5" />
      </div>
      <div className="space-y-2">
        <div className="h-5 animate-pulse rounded bg-white/5" />
        <div className="h-5 animate-pulse rounded bg-white/5" />
      </div>
      <div className="h-12 animate-pulse rounded bg-white/5" />
    </div>
  );
}

// --------------- Main Component ---------------

export default function SmartMoneyFlowWidget() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError, refetch } = useQuery<SmartMoneyData>({
    queryKey: ["smart-money-flow", symbol],
    queryFn: () => fetchSmartMoneyFlow(symbol),
    refetchInterval: 15 * 60_000, // 15 minutes
    retry: 2,
  });

  const handleRetry = useCallback(() => {
    void refetch();
  }, [refetch]);

  const signalKey = (data?.signal ?? "NEUTRAL") as SignalType;
  const signalConfig =
    SIGNAL_CONFIG[signalKey] ?? SIGNAL_CONFIG.NEUTRAL;

  return (
    <div className="rounded-lg border border-border bg-gray-900 p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">
            Smart Money Flow
          </h2>
          <p className="text-[10px] text-gray-500">refresh 15m</p>
        </div>
        <select
          value={symbol}
          onChange={(e) => { setSymbol(e.target.value); }}
          className="rounded border border-border bg-gray-800 px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
          aria-label="Select symbol for smart money flow"
        >
          {SYMBOL_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {/* Error */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded bg-red-500/10 px-3 py-2">
          <span className="text-xs text-red-400">
            Failed to load flow data
          </span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs text-red-400 underline hover:text-red-300"
            aria-label="Retry"
          >
            Retry
          </button>
        </div>
      )}

      {isLoading && <SmartMoneySkeleton />}

      {data && (
        <div className="space-y-3">
          {/* Bias gauge */}
          <div className="flex justify-center">
            <BiasGauge bias={data.bias} />
          </div>

          {/* Signal badge */}
          <div
            className={`rounded border ${signalConfig.border} ${signalConfig.bg} px-3 py-2 text-center`}
          >
            <span
              className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${signalConfig.badge}`}
            >
              {signalKey.replace(/_/g, " ")}
            </span>
            <p className="mt-1 text-xs text-gray-300">{signalConfig.label}</p>
          </div>

          {/* Flow bars */}
          <div className="space-y-2">
            <FlowBar
              label="Institutional Hours"
              ratio={data.institutional_buy_ratio}
              color="text-blue-400"
            />
            <FlowBar
              label="Retail Hours"
              ratio={data.retail_buy_ratio}
              color="text-purple-400"
            />
          </div>

          {/* Confidence */}
          <div>
            <div className="mb-1 flex justify-between text-[10px] text-gray-500">
              <span>Confidence</span>
              <span className="font-mono text-gray-300">
                {(data.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-700">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  data.confidence >= 0.7
                    ? "bg-blue-500"
                    : data.confidence >= 0.5
                      ? "bg-yellow-500"
                      : "bg-gray-500"
                }`}
                style={{ width: `${data.confidence * 100}%` }}
              />
            </div>
          </div>

          {/* Description */}
          <p className="text-xs italic text-gray-400 leading-relaxed">
            {data.description}
          </p>
        </div>
      )}
    </div>
  );
}
