/**
 * P&L Attribution Heatmap (Hour × Weekday)
 * 24×7 grid colored by average P&L per hour-of-day and day-of-week.
 * Reveals when the bot performs best and worst.
 */

import { useQuery } from "@tanstack/react-query";
import { fetchClosedPositions } from "../../api/client";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

interface CellData {
  total: number;
  count: number;
}

function buildGrid(positions: { pnl_pct?: number | null; closed_at?: string | null }[]) {
  const grid: Record<string, CellData> = {};
  for (let d = 0; d < 7; d++) {
    for (let h = 0; h < 24; h++) {
      grid[`${d}-${h}`] = { total: 0, count: 0 };
    }
  }
  for (const p of positions) {
    if (!p.closed_at || p.pnl_pct == null) continue;
    const dt = new Date(p.closed_at);
    const key = `${dt.getUTCDay()}-${dt.getUTCHours()}`;
    if (grid[key]) {
      grid[key].total += p.pnl_pct;
      grid[key].count += 1;
    }
  }
  return grid;
}

function cellColor(avg: number | null): string {
  if (avg === null) return "bg-white/3";
  if (avg > 2)    return "bg-bullish/80";
  if (avg > 1)    return "bg-bullish/50";
  if (avg > 0.2)  return "bg-bullish/25";
  if (avg > -0.2) return "bg-white/8";
  if (avg > -1)   return "bg-bearish/25";
  if (avg > -2)   return "bg-bearish/50";
  return "bg-bearish/80";
}

export function PnLAttributionHeatmap() {
  const { data, isLoading } = useQuery({
    queryKey: ["closed-positions-heatmap"],
    queryFn: () => fetchClosedPositions({ limit: 500 }),
    refetchInterval: 120_000,
    staleTime: 60_000,
    retry: false,
  });

  const grid = buildGrid(data?.positions ?? []);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-2 text-sm font-semibold text-white">P&L Attribution Heatmap</h2>
      <p className="mb-3 text-[10px] text-gray-500">
        Avg P&L by hour (UTC) × weekday. Green = profitable, red = losing.
      </p>

      {isLoading ? (
        <div className="h-28 animate-pulse rounded bg-white/5" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-0.5 text-[8px]">
            <thead>
              <tr>
                <th className="w-6 text-left text-gray-600" />
                {DAYS.map((d) => (
                  <th key={d} className="text-center text-gray-500 pb-1">{d}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {HOURS.map((h) => (
                <tr key={h}>
                  <td className="text-right pr-1 text-gray-600 text-[7px]">{h}h</td>
                  {DAYS.map((_, d) => {
                    const cell = grid[`${d}-${h}`];
                    const avg = cell && cell.count > 0 ? cell.total / cell.count : null;
                    return (
                      <td
                        key={d}
                        className={`h-3 rounded-[1px] cursor-default ${cellColor(avg)}`}
                        title={avg !== null ? `${DAYS[d]} ${h}:00 UTC — avg ${avg.toFixed(2)}% (${cell?.count} trades)` : "No data"}
                      />
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 flex items-center gap-2 text-[9px] text-gray-500">
            <div className="flex items-center gap-1">
              <div className="h-2 w-3 rounded bg-bullish/80" /><span>+2%+</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-2 w-3 rounded bg-white/8" /><span>neutral</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-2 w-3 rounded bg-bearish/80" /><span>-2%-</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
