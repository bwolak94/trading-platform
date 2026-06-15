import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchAgentStatus, fetchDayTradeStatus } from "../../api/client";

interface EquityPoint {
  index: number;
  equity: number;
  drawdown: number;
  maxEquity: number;
}

const INITIAL_CAPITAL = 10_000;

export function EquityCurve() {
  const { data: swingStatus } = useQuery({
    queryKey: ["agent-status"],
    queryFn: fetchAgentStatus,
    refetchInterval: 15_000,
  });

  const { data: dayStatus } = useQuery({
    queryKey: ["day-trade-status"],
    queryFn: fetchDayTradeStatus,
    refetchInterval: 15_000,
  });

  const { equityData, totalReturn, maxDrawdown, sharpe } = useMemo(() => {
    // Gather all trades sorted by time
    const trades: { time: string; pnl_pct: number }[] = [];

    const swingTrades = (swingStatus as unknown as Record<string, unknown>)?.recent_trades;
    if (Array.isArray(swingTrades)) {
      for (const t of swingTrades) {
        const trade = t as Record<string, unknown>;
        trades.push({
          time: String(trade.timestamp ?? trade.time ?? ""),
          pnl_pct: Number(trade.pnl_pct ?? trade.pnl ?? 0),
        });
      }
    }

    const dayTrades = (dayStatus as unknown as Record<string, unknown>)?.recent_trades;
    if (Array.isArray(dayTrades)) {
      for (const t of dayTrades) {
        const trade = t as Record<string, unknown>;
        trades.push({
          time: String(trade.timestamp ?? trade.time ?? ""),
          pnl_pct: Number(trade.pnl_pct ?? trade.pnl ?? 0),
        });
      }
    }

    trades.sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());

    if (trades.length === 0) {
      return { equityData: [], totalReturn: 0, maxDrawdown: 0, sharpe: 0 };
    }

    // Build equity curve
    const points: EquityPoint[] = [
      { index: 0, equity: INITIAL_CAPITAL, drawdown: 0, maxEquity: INITIAL_CAPITAL },
    ];

    let equity = INITIAL_CAPITAL;
    let peak = INITIAL_CAPITAL;
    let worstDD = 0;
    const returns: number[] = [];

    for (let i = 0; i < trades.length; i++) {
      const trade = trades[i];
      if (!trade) continue;
      const pnl = trade.pnl_pct / 100;
      equity = equity * (1 + pnl);
      returns.push(pnl);
      if (equity > peak) peak = equity;
      const dd = ((peak - equity) / peak) * 100;
      if (dd > worstDD) worstDD = dd;

      points.push({
        index: i + 1,
        equity: Math.round(equity * 100) / 100,
        drawdown: -Math.round(dd * 100) / 100,
        maxEquity: Math.round(peak * 100) / 100,
      });
    }

    const totalRet = ((equity - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100;

    // Simplified Sharpe-like ratio (mean / std of returns)
    let sharpeVal = 0;
    if (returns.length > 1) {
      const mean = returns.reduce((s, r) => s + r, 0) / returns.length;
      const variance = returns.reduce((s, r) => s + (r - mean) ** 2, 0) / (returns.length - 1);
      const std = Math.sqrt(variance);
      sharpeVal = std > 0 ? (mean / std) * Math.sqrt(252) : 0;
    }

    return {
      equityData: points,
      totalReturn: totalRet,
      maxDrawdown: worstDD,
      sharpe: sharpeVal,
    };
  }, [swingStatus, dayStatus]);

  if (equityData.length <= 1) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6 text-center text-sm text-gray-500">
        No closed trades yet -- equity curve will appear after trades complete.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4" aria-label="Equity curve chart">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <h3 className="text-sm font-semibold text-white">Equity Curve</h3>
        <div className="flex gap-4 text-xs">
          <div className="text-center">
            <div
              className={`text-sm font-bold ${totalReturn >= 0 ? "text-green-400" : "text-red-400"}`}
            >
              {totalReturn >= 0 ? "+" : ""}
              {totalReturn.toFixed(2)}%
            </div>
            <div className="text-gray-500">Total Return</div>
          </div>
          <div className="text-center">
            <div className="text-sm font-bold text-red-400">-{maxDrawdown.toFixed(2)}%</div>
            <div className="text-gray-500">Max Drawdown</div>
          </div>
          <div className="text-center">
            <div className="text-sm font-bold text-white">{sharpe.toFixed(2)}</div>
            <div className="text-gray-500">Sharpe Ratio</div>
          </div>
        </div>
      </div>

      <div style={{ width: "100%", height: 250 }}>
        <ResponsiveContainer>
          <ComposedChart data={equityData} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
            <XAxis dataKey="index" tick={{ fill: "#6b7280", fontSize: 10 }} />
            <YAxis
              yAxisId="equity"
              orientation="left"
              tick={{ fill: "#6b7280", fontSize: 10 }}
              domain={["dataMin", "dataMax"]}
            />
            <YAxis
              yAxisId="dd"
              orientation="right"
              tick={{ fill: "#6b7280", fontSize: 10 }}
              domain={["dataMin", 0]}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#1e1e2e",
                border: "1px solid #333",
                borderRadius: 8,
                fontSize: 12,
                color: "#fff",
              }}
              formatter={(value: number, name: string) => {
                if (name === "equity") return [`$${value.toFixed(2)}`, "Equity"];
                if (name === "drawdown") return [`${value.toFixed(2)}%`, "Drawdown"];
                return [value, name];
              }}
            />
            <Line
              yAxisId="equity"
              type="monotone"
              dataKey="equity"
              stroke="#22c55e"
              strokeWidth={2}
              dot={false}
            />
            <Area
              yAxisId="dd"
              type="monotone"
              dataKey="drawdown"
              fill="rgba(239,68,68,0.2)"
              stroke="#ef4444"
              strokeWidth={1}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
