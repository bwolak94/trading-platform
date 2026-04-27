/**
 * B14: Signal Forward Test Tracker
 *
 * After a signal is generated, tracks its forward price path for 24h with
 * markers at TP1, TP2, and SL levels.  Mini-chart per signal.
 */

import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface ForwardPath {
  signal_id: string;
  asset: string;
  direction: string;
  entry_price: number;
  tp1: number;
  tp2: number;
  sl: number;
  generated_at: string;
  price_path: { t: number; price: number }[];
  outcome: "TP1_HIT" | "TP2_HIT" | "SL_HIT" | "ACTIVE" | "EXPIRED";
}

async function fetchForwardPaths(): Promise<ForwardPath[]> {
  const resp = await fetch("/api/v1/signals/forward-paths?hours=24&limit=5");
  if (!resp.ok) throw new Error("Failed to fetch forward paths");
  return resp.json();
}

const OUTCOME_COLORS: Record<string, string> = {
  TP2_HIT: "#16a34a",
  TP1_HIT: "#22c55e",
  SL_HIT: "#ef4444",
  ACTIVE: "#22d3ee",
  EXPIRED: "#64748b",
};

interface MiniChartProps {
  path: ForwardPath;
}

function MiniChart({ path }: MiniChartProps) {
  const prices = path.price_path.map((p) => p.price);
  const yMin = Math.min(...prices, path.sl) * 0.999;
  const yMax = Math.max(...prices, path.tp2 || path.tp1) * 1.001;

  return (
    <div className="rounded border border-border bg-background/50 p-3">
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="font-semibold text-gray-200">{path.asset}</span>
        <span className={path.direction === "LONG" ? "text-bullish" : "text-bearish"}>
          {path.direction}
        </span>
        <span
          className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
          style={{ background: `${OUTCOME_COLORS[path.outcome]}20`, color: OUTCOME_COLORS[path.outcome] }}
        >
          {path.outcome}
        </span>
      </div>

      <ResponsiveContainer width="100%" height={90}>
        <LineChart data={path.price_path} margin={{ top: 2, right: 4, bottom: 2, left: 0 }}>
          <CartesianGrid strokeDasharray="2 2" stroke="#334155" />
          <XAxis dataKey="t" tick={false} />
          <YAxis domain={[yMin, yMax]} tick={{ fontSize: 8, fill: "#94a3b8" }} width={45} tickFormatter={(v) => v.toLocaleString()} />
          <Tooltip
            contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 10 }}
            formatter={(v: number) => [v.toLocaleString(), "Price"]}
          />
          <ReferenceLine y={path.entry_price} stroke="#94a3b8" strokeDasharray="3 3" label={{ value: "E", position: "left", fontSize: 8, fill: "#94a3b8" }} />
          <ReferenceLine y={path.tp1} stroke="#22c55e" strokeDasharray="3 3" label={{ value: "TP1", position: "right", fontSize: 8, fill: "#22c55e" }} />
          {path.tp2 && <ReferenceLine y={path.tp2} stroke="#16a34a" strokeDasharray="3 3" label={{ value: "TP2", position: "right", fontSize: 8, fill: "#16a34a" }} />}
          <ReferenceLine y={path.sl} stroke="#ef4444" strokeDasharray="3 3" label={{ value: "SL", position: "left", fontSize: 8, fill: "#ef4444" }} />
          <Line type="monotone" dataKey="price" stroke="#22d3ee" strokeWidth={1.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SignalForwardTestTracker() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["signal-forward-paths"],
    queryFn: fetchForwardPaths,
    staleTime: 60_000,
    refetchInterval: 2 * 60 * 1000,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold text-gray-200">Signal Forward Test Tracker</h3>
      <p className="mb-3 text-xs text-gray-400">
        Last 5 signals — 24h price path with TP1, TP2, SL markers
      </p>

      {isLoading && <div className="flex h-24 items-center justify-center text-xs text-gray-500">Loading…</div>}
      {isError && <div className="flex h-24 items-center justify-center text-xs text-bearish">Failed to load</div>}

      {!isLoading && !isError && data && (
        <div className="space-y-3">
          {data.length === 0 ? (
            <div className="py-8 text-center text-xs text-gray-500">
              No signal history yet
            </div>
          ) : (
            data.map((path) => <MiniChart key={path.signal_id} path={path} />)
          )}
        </div>
      )}
    </div>
  );
}
