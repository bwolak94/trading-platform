/**
 * Correlation Shock Detector
 * Alerts when the rolling 1h correlation between two assets drops
 * more than 0.4 in a single candle — a potential crisis/divergence signal.
 */

import { useQuery } from "@tanstack/react-query";
import axios from "axios";

interface CorrelationSnapshot {
  pair: string;
  assetA: string;
  assetB: string;
  corr_current: number;
  corr_prev: number;
  delta: number;
  shock: boolean;
}

const PAIRS: [string, string][] = [
  ["BTCUSDT", "ETHUSDT"],
  ["BTCUSDT", "SOLUSDT"],
  ["ETHUSDT", "SOLUSDT"],
  ["BTCUSDT", "BNBUSDT"],
];

async function fetchCandles(symbol: string, limit = 60): Promise<number[]> {
  const { data } = await axios.get(`/api/v1/market/ohlcv`, {
    params: { symbol, timeframe: "1h", limit },
  });
  const candles = data.candles ?? data.data ?? data ?? [];
  return (candles as { close: number }[]).map((c) => c.close);
}

function pearson(x: number[], y: number[]): number {
  const n = Math.min(x.length, y.length);
  if (n < 4) return 0;
  const xa = x.slice(-n), ya = y.slice(-n);
  const mx = xa.reduce((s, v) => s + v, 0) / n;
  const my = ya.reduce((s, v) => s + v, 0) / n;
  const num = xa.reduce((s, v, i) => s + (v - mx) * (ya[i]! - my), 0);
  const dx = Math.sqrt(xa.reduce((s, v) => s + (v - mx) ** 2, 0));
  const dy = Math.sqrt(ya.reduce((s, v) => s + (v - my) ** 2, 0));
  return dx && dy ? num / (dx * dy) : 0;
}

async function fetchCorrelationShocks(): Promise<CorrelationSnapshot[]> {
  const results = await Promise.allSettled(
    PAIRS.map(async ([a, b]) => {
      const [pricesA, pricesB] = await Promise.all([fetchCandles(a, 62), fetchCandles(b, 62)]);
      const corr_current = pearson(pricesA.slice(-30), pricesB.slice(-30));
      const corr_prev = pearson(pricesA.slice(-60, -30), pricesB.slice(-60, -30));
      const delta = corr_current - corr_prev;
      return {
        pair: `${a.replace("USDT", "")}/${b.replace("USDT", "")}`,
        assetA: a,
        assetB: b,
        corr_current: parseFloat(corr_current.toFixed(3)),
        corr_prev: parseFloat(corr_prev.toFixed(3)),
        delta: parseFloat(delta.toFixed(3)),
        shock: Math.abs(delta) >= 0.3,
      };
    }),
  );
  return results
    .filter((r): r is PromiseFulfilledResult<CorrelationSnapshot> => r.status === "fulfilled")
    .map((r) => r.value);
}

function CorrBar({ value }: { value: number }) {
  const pct = Math.abs(value) * 50;
  const color = value > 0.5 ? "bg-bullish" : value < -0.3 ? "bg-bearish" : "bg-gray-500";
  return (
    <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-white/5">
      <div
        className={`absolute top-0 h-full rounded-full ${color}`}
        style={{ width: `${pct}%`, left: value >= 0 ? "50%" : `${50 - pct}%` }}
      />
    </div>
  );
}

export function CorrelationShockPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["correlation-shocks"],
    queryFn: fetchCorrelationShocks,
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });

  const shocks = (data ?? []).filter((d) => d.shock);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Correlation Shock Detector</h2>
        {shocks.length > 0 && (
          <span className="rounded bg-amber-400/20 px-2 py-0.5 text-xs font-bold text-amber-400">
            {shocks.length} shock{shocks.length > 1 ? "s" : ""}
          </span>
        )}
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        Alerts when 30h rolling correlation between two assets shifts by ≥0.3 — a potential crisis or regime break signal.
      </p>

      {isError && <p className="text-xs text-bearish">Data unavailable</p>}

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-white/5" />)}
        </div>
      ) : (
        <div className="space-y-2">
          {(data ?? []).map((s) => (
            <div
              key={s.pair}
              className={`rounded border px-3 py-2 ${s.shock ? "border-amber-400/40 bg-amber-400/5" : "border-border bg-background"}`}
            >
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className={`font-semibold ${s.shock ? "text-amber-300" : "text-gray-200"}`}>
                  {s.shock && "⚡ "}{s.pair}
                </span>
                <span className={`font-mono text-sm font-bold ${s.corr_current > 0.5 ? "text-bullish" : s.corr_current < 0 ? "text-bearish" : "text-gray-300"}`}>
                  {s.corr_current.toFixed(2)}
                </span>
              </div>
              <CorrBar value={s.corr_current} />
              <div className="mt-1 flex justify-between text-[10px] text-gray-500">
                <span>prev {s.corr_prev.toFixed(2)}</span>
                <span className={s.delta < -0.3 ? "text-bearish" : s.delta > 0.3 ? "text-bullish" : "text-gray-500"}>
                  Δ {s.delta >= 0 ? "+" : ""}{s.delta.toFixed(2)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
