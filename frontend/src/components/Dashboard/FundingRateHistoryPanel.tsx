/**
 * Funding Rate History Chart
 * 30-day sparkline of funding rate for a selected asset
 * with ±1σ bands and the current rate highlighted.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer } from "recharts";
import axios from "axios";

interface FundingPoint {
  ts: number;
  date: string;
  rate: number;
}

interface FundingHistoryRaw {
  symbol: string;
  fundingRate: string;
  fundingTime: number;
}

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];

async function fetchFundingHistory(symbol: string): Promise<FundingPoint[]> {
  const { data } = await axios.get<FundingHistoryRaw[]>(
    "https://fapi.binance.com/fapi/v1/fundingRate",
    { params: { symbol, limit: 90 } },
  );
  return data.map((d) => ({
    ts: d.fundingTime,
    date: new Date(d.fundingTime).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    rate: parseFloat(d.fundingRate) * 100,
  }));
}

export function FundingRateHistoryPanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading } = useQuery({
    queryKey: ["funding-history", symbol],
    queryFn: () => fetchFundingHistory(symbol),
    refetchInterval: 5 * 60_000,
    staleTime: 60_000,
    retry: false,
  });

  const rates = data?.map((d) => d.rate) ?? [];
  const mean = rates.length ? rates.reduce((a, b) => a + b, 0) / rates.length : 0;
  const std = rates.length > 1
    ? Math.sqrt(rates.reduce((s, r) => s + (r - mean) ** 2, 0) / rates.length)
    : 0;
  const current = rates[rates.length - 1] ?? 0;
  const color = current > 0 ? "#22c55e" : "#ef4444";

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Funding Rate History</h2>
        <select
          value={symbol}
          onChange={(e) => { setSymbol(e.target.value); }}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none"
          aria-label="Select asset"
        >
          {SYMBOLS.map((s) => <option key={s} value={s}>{s.replace("USDT", "")}</option>)}
        </select>
      </div>

      <div className="mb-3 grid grid-cols-3 gap-2 text-center text-xs">
        <div className="rounded bg-background py-1.5">
          <p className="text-gray-500">Current</p>
          <p className={`font-mono font-bold`} style={{ color }}>{current.toFixed(4)}%</p>
        </div>
        <div className="rounded bg-background py-1.5">
          <p className="text-gray-500">30d Mean</p>
          <p className="font-mono font-bold text-gray-300">{mean.toFixed(4)}%</p>
        </div>
        <div className="rounded bg-background py-1.5">
          <p className="text-gray-500">±1σ Band</p>
          <p className="font-mono text-[10px] text-gray-400">
            {(mean - std).toFixed(3)} / {(mean + std).toFixed(3)}
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="h-28 animate-pulse rounded bg-white/5" />
      ) : (
        <ResponsiveContainer width="100%" height={110}>
          <AreaChart data={data ?? []} margin={{ top: 2, right: 4, left: -24, bottom: 0 }}>
            <defs>
              <linearGradient id="fundingGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" tick={{ fontSize: 8, fill: "#6b7280" }} interval={14} />
            <YAxis tick={{ fontSize: 8, fill: "#6b7280" }} tickFormatter={(v) => `${v.toFixed(3)}%`} />
            <Tooltip
              contentStyle={{ background: "#1a1a2e", border: "1px solid #374151", fontSize: 10 }}
              formatter={(v: number) => [`${v.toFixed(4)}%`, "Funding Rate"]}
            />
            <ReferenceLine y={mean} stroke="#6b7280" strokeDasharray="3 3" />
            <ReferenceLine y={mean + std} stroke="#374151" strokeDasharray="2 2" />
            <ReferenceLine y={mean - std} stroke="#374151" strokeDasharray="2 2" />
            <Area type="monotone" dataKey="rate" stroke={color} fill="url(#fundingGrad)" strokeWidth={1.5} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
