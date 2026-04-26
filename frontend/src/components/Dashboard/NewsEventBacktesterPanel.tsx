/**
 * News Event Backtester Panel
 * Shows how price historically moved ±4h around past FOMC/CPI/NFP events.
 * Uses the /api/v1/backtest/news-events/{symbol} endpoint.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import axios from "axios";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, Cell, ResponsiveContainer } from "recharts";
import { fmtPct, colorClass } from "../../lib/format";

interface EventInstance {
  event_date: string;
  gross_move_pct: number;
  net_move_pct: number;
  direction: "UP" | "DOWN";
}

interface NewsBacktestData {
  symbol: string;
  event_type: string;
  events_analysed: number;
  up_count: number;
  down_count: number;
  avg_gross_move_pct: number;
  avg_net_move_pct: number;
  max_move_pct: number;
  slippage_bps: number;
  round_trip_cost_bps: number;
  instances: EventInstance[];
}

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
const EVENT_TYPES = ["FOMC", "CPI", "NFP"];

async function fetchNewsBacktest(symbol: string, event_type: string): Promise<NewsBacktestData> {
  const { data } = await axios.get(`/api/v1/backtest/news-events/${symbol}`, {
    params: { event_type, window_hours: 4 },
  });
  return data.data as NewsBacktestData;
}

export function NewsEventBacktesterPanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [eventType, setEventType] = useState("CPI");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["news-backtest", symbol, eventType],
    queryFn: () => fetchNewsBacktest(symbol, eventType),
    staleTime: 10 * 60_000,
    retry: false,
  });

  const chartData = (data?.instances ?? []).map((inst) => ({
    date: inst.event_date,
    gross: parseFloat(inst.gross_move_pct.toFixed(2)),
    net: parseFloat(inst.net_move_pct.toFixed(2)),
  }));

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">News Event Backtester</h2>
        <div className="flex gap-1.5">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none"
            aria-label="Select asset"
          >
            {SYMBOLS.map((s) => <option key={s} value={s}>{s.replace("USDT", "")}</option>)}
          </select>
          <select
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none"
            aria-label="Select event type"
          >
            {EVENT_TYPES.map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
        </div>
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        Price move ±4h around past {eventType} events. Net of {data?.round_trip_cost_bps?.toFixed(0) ?? "~10"} bps slippage + fees.
      </p>

      {isError && <p className="text-xs text-bearish">Backtest data unavailable</p>}

      {isLoading ? (
        <div className="h-36 animate-pulse rounded bg-white/5" />
      ) : data ? (
        <>
          <div className="mb-3 grid grid-cols-2 gap-2 text-center text-xs sm:grid-cols-4">
            <div className="rounded bg-background py-1.5">
              <p className="text-gray-500">Events</p>
              <p className="font-mono font-bold text-white">{data.events_analysed}</p>
            </div>
            <div className="rounded bg-background py-1.5">
              <p className="text-gray-500">Up / Down</p>
              <p className="font-mono font-bold text-white">{data.up_count}/{data.down_count}</p>
            </div>
            <div className="rounded bg-background py-1.5">
              <p className="text-gray-500">Avg Gross</p>
              <p className={`font-mono font-bold ${colorClass(data.avg_gross_move_pct)}`}>
                {fmtPct(data.avg_gross_move_pct, { showSign: true, decimals: 2 })}
              </p>
            </div>
            <div className="rounded bg-background py-1.5">
              <p className="text-gray-500">Avg Net</p>
              <p className={`font-mono font-bold ${colorClass(data.avg_net_move_pct)}`}>
                {fmtPct(data.avg_net_move_pct, { showSign: true, decimals: 2 })}
              </p>
            </div>
          </div>

          <ResponsiveContainer width="100%" height={130}>
            <BarChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <XAxis dataKey="date" tick={{ fontSize: 8, fill: "#6b7280" }} />
              <YAxis tick={{ fontSize: 8, fill: "#6b7280" }} tickFormatter={(v) => `${v}%`} />
              <Tooltip
                contentStyle={{ background: "#1a1a2e", border: "1px solid #374151", fontSize: 10 }}
                formatter={(v: number, name: string) => [`${v.toFixed(2)}%`, name === "gross" ? "Gross move" : "Net (after costs)"]}
              />
              <ReferenceLine y={0} stroke="#374151" />
              <Bar dataKey="gross" name="gross" opacity={0.5} radius={[2, 2, 0, 0]}>
                {chartData.map((d, i) => <Cell key={i} fill={d.gross >= 0 ? "#22c55e" : "#ef4444"} />)}
              </Bar>
              <Bar dataKey="net" name="net" radius={[2, 2, 0, 0]}>
                {chartData.map((d, i) => <Cell key={i} fill={d.net >= 0 ? "#4ade80" : "#f87171"} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </>
      ) : null}
    </div>
  );
}
