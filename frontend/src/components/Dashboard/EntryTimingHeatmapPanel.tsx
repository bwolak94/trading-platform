import { useQuery } from "@tanstack/react-query";
import { fetchEntryTimingHeatmap } from "../../api/client";
import type { TimingCell } from "../../api/client";

/**
 * Map a win rate [0, 1] to a CSS background color via an HSL gradient.
 * 0 → red (hue 0), 0.5 → yellow (hue 50), 1 → bright green (hue 120).
 */
function winRateBg(winRate: number): string {
  // Clamp to [0, 1]
  const w = Math.max(0, Math.min(1, winRate));
  const hue = Math.round(w * 120); // 0=red, 60=yellow, 120=green
  const saturation = 75;
  const lightness = 30 + Math.round(w * 15); // 30%→45%
  return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
}

function winRateText(_winRate: number): string {
  // Dark text only on very light cells (none expected here, keep white)
  return "rgba(255,255,255,0.9)";
}

interface CellMap {
  [hour: number]: {
    [day: number]: TimingCell;
  };
}

export function EntryTimingHeatmapPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["entry-timing-heatmap"],
    queryFn: fetchEntryTimingHeatmap,
    refetchInterval: 60_000,
  });

  const days = data?.days ?? ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  // Build a lookup map: cellMap[hour][day]
  const cellMap: CellMap = {};
  for (const cell of data?.matrix ?? []) {
    const hourMap = cellMap[cell.hour] ?? {};
    cellMap[cell.hour] = hourMap;
    hourMap[cell.day] = cell;
  }

  const hasData = (data?.matrix ?? []).some((c) => c.total_trades > 0);

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">
          Entry Timing Heatmap (UTC)
        </h2>
        <p className="text-xs text-muted-foreground">
          Win rate by hour × day of week
        </p>
      </div>

      {isLoading ? (
        <div
          className="flex h-48 items-center justify-center text-sm text-muted-foreground"
          aria-busy="true"
          aria-label="Loading entry timing heatmap"
        >
          Loading…
        </div>
      ) : !hasData ? (
        <div className="flex h-48 items-center justify-center rounded-lg border border-border/50 bg-surface/30 text-sm text-muted-foreground">
          No closed trades yet
        </div>
      ) : (
        <div className="overflow-x-auto" role="region" aria-label="Entry timing heatmap">
          <table
            className="w-full border-collapse text-[10px]"
            role="grid"
            aria-label="Win rate by entry hour and day of week"
          >
            <thead>
              <tr>
                {/* Hour label column */}
                <th
                  scope="col"
                  className="w-8 pb-1 pr-1 text-right font-medium text-muted-foreground"
                  aria-label="Hour (UTC)"
                >
                  h
                </th>
                {days.map((day) => (
                  <th
                    key={day}
                    scope="col"
                    className="pb-1 px-0.5 text-center font-medium text-muted-foreground min-w-[32px]"
                  >
                    {day}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 24 }, (_, h) => (
                <tr key={h}>
                  <th
                    scope="row"
                    className="pr-1 text-right font-mono text-muted-foreground/70 select-none"
                    aria-label={`Hour ${h} UTC`}
                  >
                    {String(h).padStart(2, "0")}
                  </th>
                  {Array.from({ length: 7 }, (_, d) => {
                    const cell = cellMap[h]?.[d];
                    const hasTrades = (cell?.total_trades ?? 0) > 0;
                    const wr = cell?.win_rate ?? null;

                    return (
                      <td
                        key={d}
                        className="px-0.5 py-px"
                        title={
                          hasTrades && wr !== null
                            ? `${days[d]} ${String(h).padStart(2, "0")}:00 UTC — ${(wr * 100).toFixed(0)}% win rate (${cell!.total_trades} trades)`
                            : `${days[d]} ${String(h).padStart(2, "0")}:00 UTC — no data`
                        }
                      >
                        <div
                          className="flex h-6 min-w-[28px] items-center justify-center rounded text-[9px] font-medium leading-none"
                          style={
                            hasTrades && wr !== null
                              ? {
                                  backgroundColor: winRateBg(wr),
                                  color: winRateText(wr),
                                }
                              : { backgroundColor: "rgba(255,255,255,0.04)", color: "rgba(255,255,255,0.2)" }
                          }
                          aria-label={
                            hasTrades && wr !== null
                              ? `${(wr * 100).toFixed(0)}% win rate`
                              : "no data"
                          }
                        >
                          {hasTrades && wr !== null
                            ? `${(wr * 100).toFixed(0)}%`
                            : "—"}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>

          {/* Legend */}
          <div className="mt-3 flex items-center gap-2" aria-label="Color legend">
            <span className="text-[10px] text-muted-foreground">Win rate:</span>
            <div className="flex items-center gap-1">
              {[0, 0.25, 0.5, 0.75, 1].map((val) => (
                <div
                  key={val}
                  className="flex h-4 w-8 items-center justify-center rounded text-[9px] font-medium text-white/80"
                  style={{ backgroundColor: winRateBg(val) }}
                  aria-label={`${(val * 100).toFixed(0)}%`}
                >
                  {(val * 100).toFixed(0)}%
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
