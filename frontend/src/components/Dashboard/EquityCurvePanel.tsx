import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { fetchEquityCurve } from "../../api/client";
import type { EquityPoint } from "../../api/client";

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: EquityPoint }[];
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0]!.payload;
  return (
    <div className="rounded-lg border border-border bg-background/95 px-3 py-2 text-xs shadow-lg backdrop-blur-sm">
      <p className="font-medium text-foreground">{`Trade #${d.trade_count}`}</p>
      <p className="text-muted-foreground">{new Date(d.time).toLocaleString()}</p>
      <p className={d.equity >= 100 ? "text-green-400" : "text-red-400"}>
        Equity: {d.equity.toFixed(2)}%
      </p>
      <p className={d.pnl_pct >= 0 ? "text-green-400" : "text-red-400"}>
        Trade PnL: {d.pnl_pct >= 0 ? "+" : ""}
        {d.pnl_pct.toFixed(2)}%
      </p>
    </div>
  );
}

export function EquityCurvePanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["equity-curve"],
    queryFn: fetchEquityCurve,
    refetchInterval: 30_000,
  });

  const curve = data?.equity_curve ?? [];

  // A6: Memoize expensive series calculations keyed on data length + last timestamp
  const { currentEquity, isProfit, peakEquity, drawdown } = useMemo(() => {
    const last = curve.length > 0 ? curve[curve.length - 1] : undefined;
    const equity = last?.equity ?? 100;
    const peak = curve.length > 0 ? Math.max(...curve.map((p) => p.equity)) : 100;
    const dd = peak > 0 ? ((peak - equity) / peak) * 100 : 0;
    return {
      currentEquity: equity,
      isProfit: equity >= 100,
      peakEquity: peak,
      drawdown: dd,
    };
  }, [curve.length, curve[curve.length - 1]?.time]);

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">Equity Curve</h2>
          <p className="text-xs text-muted-foreground">
            Cumulative performance from closed trades
          </p>
        </div>
        <div className="text-right">
          <span
            className={`text-lg font-bold ${isProfit ? "text-green-400" : "text-red-400"}`}
          >
            {currentEquity.toFixed(2)}%
          </span>
          <p className="text-xs text-muted-foreground">
            DD: <span className="text-red-400">{drawdown.toFixed(2)}%</span>
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
          Loading equity curve...
        </div>
      ) : curve.length === 0 ? (
        <div className="flex h-48 items-center justify-center rounded-lg border border-border/50 bg-surface/30 text-sm text-muted-foreground">
          No closed trades yet — equity curve will appear here
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={curve} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="hsl(var(--border))"
              strokeOpacity={0.4}
            />
            <XAxis
              dataKey="trade_count"
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              tickLine={false}
              label={{
                value: "Trades",
                position: "insideBottomRight",
                offset: -4,
                fontSize: 11,
                fill: "hsl(var(--muted-foreground))",
              }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              tickLine={false}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              width={48}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine
              y={100}
              stroke="hsl(var(--muted-foreground))"
              strokeDasharray="4 4"
              strokeOpacity={0.6}
            />
            <Line
              type="monotone"
              dataKey="equity"
              stroke={isProfit ? "#4ade80" : "#f87171"}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      <div className="flex gap-4 text-xs text-muted-foreground">
        <span>
          Trades: <strong className="text-foreground">{curve.length}</strong>
        </span>
        <span>
          Peak: <strong className="text-green-400">{peakEquity.toFixed(2)}%</strong>
        </span>
        <span>
          Max DD: <strong className="text-red-400">{drawdown.toFixed(2)}%</strong>
        </span>
      </div>
    </div>
  );
}
