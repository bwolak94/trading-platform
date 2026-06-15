/**
 * Cross-Asset Spread Tracker
 * BTC/ETH, ETH/SOL, BTC/BNB ratios with Bollinger-band mean-reversion signals.
 */

import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer } from "recharts";

interface OHLCBar { close: number }

async function fetchPrices(symbol: string, limit = 100): Promise<number[]> {
  const { data } = await axios.get(`/api/v1/market/ohlcv`, { params: { symbol, timeframe: "1h", limit } });
  const bars = (data.candles ?? data.data ?? data) as OHLCBar[];
  return bars.map((b) => b.close);
}

interface SpreadSeries {
  label: string;
  numerator: string;
  denominator: string;
  values: { i: number; ratio: number }[];
  current: number;
  mean: number;
  upper: number;
  lower: number;
  signal: "MEAN_REVERT_SHORT" | "MEAN_REVERT_LONG" | "NEUTRAL";
}

function bollingerBands(values: number[], period = 20, mult = 2) {
  if (values.length < period) return { mean: 0, upper: 0, lower: 0 };
  const slice = values.slice(-period);
  const mean = slice.reduce((a, b) => a + b, 0) / period;
  const std = Math.sqrt(slice.reduce((s, v) => s + (v - mean) ** 2, 0) / period);
  return { mean, upper: mean + mult * std, lower: mean - mult * std };
}

const PAIRS: [string, string, string][] = [
  ["BTC/ETH", "BTCUSDT", "ETHUSDT"],
  ["ETH/SOL", "ETHUSDT", "SOLUSDT"],
  ["BTC/BNB", "BTCUSDT", "BNBUSDT"],
];

async function fetchAllSpreads(): Promise<SpreadSeries[]> {
  const priceMap: Record<string, number[]> = {};
  const needed = [...new Set(PAIRS.flatMap(([, a, b]) => [a, b]))];
  await Promise.all(needed.map(async (sym) => { priceMap[sym] = await fetchPrices(sym); }));

  return PAIRS.map(([label, num, den]) => {
    const a = priceMap[num] ?? [];
    const b = priceMap[den] ?? [];
    const n = Math.min(a.length, b.length);
    const ratios = Array.from({ length: n }, (_, i) => (b[i] && b[i] > 0 ? (a[i]! / b[i]) : 0));
    const values = ratios.map((r, i) => ({ i, ratio: parseFloat(r.toFixed(4)) }));
    const { mean, upper, lower } = bollingerBands(ratios);
    const current = ratios[ratios.length - 1] ?? 0;
    const signal: SpreadSeries["signal"] =
      current > upper ? "MEAN_REVERT_SHORT" :
      current < lower ? "MEAN_REVERT_LONG" : "NEUTRAL";
    return { label, numerator: num, denominator: den, values: values.slice(-60), current, mean, upper, lower, signal };
  });
}

const SIGNAL_STYLE: Record<SpreadSeries["signal"], { color: string; text: string }> = {
  MEAN_REVERT_SHORT: { color: "text-bearish", text: "Short ratio" },
  MEAN_REVERT_LONG:  { color: "text-bullish", text: "Long ratio" },
  NEUTRAL:           { color: "text-gray-400", text: "Neutral" },
};

export function SpreadTrackerPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["spread-tracker"],
    queryFn: fetchAllSpreads,
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-2 text-sm font-semibold text-white">Cross-Asset Spread Tracker</h2>
      <p className="mb-3 text-[10px] text-gray-500">
        Price ratios with Bollinger bands. Outside bands = mean-reversion opportunity.
      </p>

      {isError && <p className="text-xs text-bearish">Spread data unavailable</p>}

      {isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => <div key={i} className="h-20 animate-pulse rounded bg-white/5" />)}
        </div>
      ) : (
        <div className="space-y-4">
          {(data ?? []).map((spread) => {
            const sig = SIGNAL_STYLE[spread.signal];
            return (
              <div key={spread.label} className="rounded border border-border bg-background p-3">
                <div className="mb-2 flex items-center justify-between text-xs">
                  <span className="font-semibold text-gray-200">{spread.label}</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-white">{spread.current.toFixed(4)}</span>
                    <span className={`text-[10px] font-medium ${sig.color}`}>{sig.text}</span>
                  </div>
                </div>
                <ResponsiveContainer width="100%" height={60}>
                  <LineChart data={spread.values} margin={{ top: 2, right: 4, left: -30, bottom: 0 }}>
                    <XAxis hide />
                    <YAxis tick={{ fontSize: 7, fill: "#6b7280" }} domain={["auto", "auto"]} />
                    <Tooltip
                      contentStyle={{ background: "#1a1a2e", border: "1px solid #374151", fontSize: 9 }}
                      formatter={(v: number) => [v.toFixed(4), spread.label]}
                    />
                    <ReferenceLine y={spread.mean}  stroke="#6b7280" strokeDasharray="3 3" strokeWidth={1} />
                    <ReferenceLine y={spread.upper} stroke="#ef4444" strokeDasharray="2 2" strokeWidth={1} />
                    <ReferenceLine y={spread.lower} stroke="#22c55e" strokeDasharray="2 2" strokeWidth={1} />
                    <Line type="monotone" dataKey="ratio" stroke="#6366f1" strokeWidth={1.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
