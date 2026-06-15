/**
 * Open Interest Momentum Panel
 * Shows OI rate-of-change over 1h/4h/24h with directional signal.
 * Rising OI + rising price = strong trend confirmation.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import axios from "axios";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface OIWindow {
  roc_pct: number;
  oi_now: number;
  oi_then: number;
  signal: string;
}

interface OIMomentumData {
  symbol: string;
  oi_usd_million: number;
  "1h": OIWindow;
  "4h": OIWindow;
  "24h": OIWindow;
  snapshots: { ts: number; oi: number; oi_usd: number }[];
}

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];

const SIGNAL_STYLE: Record<string, { color: string; bg: string }> = {
  STRONG_BULLISH: { color: "text-bullish", bg: "bg-bullish/15" },
  BULLISH:        { color: "text-bullish", bg: "bg-bullish/8" },
  NEUTRAL:        { color: "text-gray-400", bg: "bg-white/5" },
  BEARISH:        { color: "text-bearish", bg: "bg-bearish/8" },
  STRONG_BEARISH: { color: "text-bearish", bg: "bg-bearish/15" },
};

async function fetchOIMomentum(symbol: string): Promise<OIMomentumData> {
  const { data } = await axios.get(`/api/v1/market/oi-momentum/${symbol}`);
  return data.data as OIMomentumData;
}

function WindowBadge({ label, window: w }: { label: string; window: OIWindow }) {
  const style = SIGNAL_STYLE[w.signal] ?? { color: "text-gray-400", bg: "bg-white/5" };
  return (
    <div className={`rounded border border-border px-2 py-2 text-center ${style.bg}`}>
      <p className="text-[10px] text-gray-500">{label}</p>
      <p className={`font-mono text-sm font-bold ${style.color}`}>
        {w.roc_pct >= 0 ? "+" : ""}{w.roc_pct.toFixed(2)}%
      </p>
      <p className={`text-[9px] font-medium ${style.color}`}>{w.signal.replace("_", " ")}</p>
    </div>
  );
}

export function OIMomentumPanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["oi-momentum", symbol],
    queryFn: () => fetchOIMomentum(symbol),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });

  const chartData = (data?.snapshots ?? []).map((s, i) => ({
    i,
    oi_m: parseFloat((s.oi_usd / 1e6).toFixed(1)),
  }));

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">OI Momentum</h2>
        <select
          value={symbol}
          onChange={(e) => { setSymbol(e.target.value); }}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none"
          aria-label="Select asset"
        >
          {SYMBOLS.map((s) => <option key={s} value={s}>{s.replace("USDT", "")}</option>)}
        </select>
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        OI rate-of-change. Rising OI + price = trend confirmation. Falling OI = weakening conviction.
      </p>

      {isError && <p className="text-xs text-bearish mb-2">OI data unavailable</p>}

      {isLoading ? (
        <div className="h-28 animate-pulse rounded bg-white/5" />
      ) : data ? (
        <>
          {data.oi_usd_million > 0 && (
            <p className="mb-2 text-xs text-gray-500">
              Open Interest: <span className="font-mono text-white">${data.oi_usd_million.toFixed(0)}M</span>
            </p>
          )}

          <div className="mb-3 grid grid-cols-3 gap-2">
            <WindowBadge label="1h ROC" window={data["1h"]} />
            <WindowBadge label="4h ROC" window={data["4h"]} />
            <WindowBadge label="24h ROC" window={data["24h"]} />
          </div>

          {chartData.length > 4 && (
            <ResponsiveContainer width="100%" height={80}>
              <AreaChart data={chartData} margin={{ top: 2, right: 4, left: -30, bottom: 0 }}>
                <defs>
                  <linearGradient id="oiGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis hide />
                <YAxis tick={{ fontSize: 8, fill: "#6b7280" }} tickFormatter={(v) => `$${v}M`} />
                <Tooltip
                  contentStyle={{ background: "#1a1a2e", border: "1px solid #374151", fontSize: 10 }}
                  formatter={(v: number) => [`$${v}M`, "OI"]}
                />
                <Area type="monotone" dataKey="oi_m" stroke="#6366f1" fill="url(#oiGrad)" strokeWidth={1.5} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </>
      ) : null}
    </div>
  );
}
