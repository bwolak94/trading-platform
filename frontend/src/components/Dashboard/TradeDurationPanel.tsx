import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchTradeDuration } from "../../api/client";

/** Distinct palette for up to 8 strategies. */
const STRATEGY_COLORS: readonly string[] = [
  "#6366f1", // indigo
  "#22d3ee", // cyan
  "#f59e0b", // amber
  "#10b981", // emerald
  "#f43f5e", // rose
  "#a78bfa", // violet
  "#fb923c", // orange
  "#34d399", // teal
];

export function TradeDurationPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["trade-duration"],
    queryFn: fetchTradeDuration,
    refetchInterval: 60_000,
  });

  const buckets = data?.buckets ?? [];
  const byStrategy = data?.by_strategy ?? {};
  const strategies = Object.keys(byStrategy);

  /** Reshape into recharts-friendly [{bucket, strategy1: count, strategy2: count, …}] */
  const chartData = buckets.map((bucket) => {
    const entry: Record<string, string | number> = { bucket };
    for (const strategy of strategies) {
      entry[strategy] = byStrategy[strategy]?.[bucket] ?? 0;
    }
    return entry;
  });

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">
          Trade Duration Distribution
        </h2>
        <p className="text-xs text-muted-foreground">
          Closed trade counts grouped by hold duration
        </p>
      </div>

      {isLoading ? (
        <div
          className="flex h-48 items-center justify-center text-sm text-muted-foreground"
          aria-busy="true"
          aria-label="Loading trade duration data"
        >
          Loading…
        </div>
      ) : strategies.length === 0 ? (
        <div className="flex h-48 items-center justify-center rounded-lg border border-border/50 bg-surface/30 text-sm text-muted-foreground">
          No closed trades yet
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart
            data={chartData}
            margin={{ top: 4, right: 8, left: 0, bottom: 4 }}
            aria-label="Trade duration distribution bar chart"
          >
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis
              dataKey="bucket"
              tick={{ fill: "#9ca3af", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: "#9ca3af", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
              width={28}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#0f1117",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              labelStyle={{ color: "#e5e7eb", marginBottom: "4px" }}
              cursor={{ fill: "rgba(255,255,255,0.04)" }}
            />
            <Legend
              wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }}
              iconSize={10}
              iconType="circle"
            />
            {strategies.map((strategy, idx) => (
              <Bar
                key={strategy}
                dataKey={strategy}
                stackId="a"
                fill={STRATEGY_COLORS[idx % STRATEGY_COLORS.length]}
                radius={idx === strategies.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
