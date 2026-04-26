/**
 * Position Journal Tagging
 * Tag closed trades (FOMO, news-driven, good entry, revenge trade, etc.)
 * and view tag-grouped P&L stats. Tags persist in localStorage.
 */

import { useReducer, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchClosedPositions } from "../../api/client";
import { fmtPct, colorClass } from "../../lib/format";

const TAGS = ["Good Entry", "FOMO", "News-Driven", "Revenge Trade", "TP Hit", "Stop Hunt", "Oversize"] as const;
type Tag = (typeof TAGS)[number];

const LS_KEY = "trade_journal_tags_v1";

function loadTags(): Record<string, Tag[]> {
  try { return JSON.parse(localStorage.getItem(LS_KEY) ?? "{}"); } catch { return {}; }
}

function saveTags(tags: Record<string, Tag[]>) {
  localStorage.setItem(LS_KEY, JSON.stringify(tags));
}

type Action =
  | { type: "toggle"; id: string; tag: Tag }
  | { type: "clear"; id: string };

function reducer(state: Record<string, Tag[]>, action: Action): Record<string, Tag[]> {
  let next: Record<string, Tag[]>;
  if (action.type === "toggle") {
    const existing = state[action.id] ?? [];
    const has = existing.includes(action.tag);
    next = { ...state, [action.id]: has ? existing.filter((t) => t !== action.tag) : [...existing, action.tag] };
  } else {
    next = { ...state, [action.id]: [] };
  }
  saveTags(next);
  return next;
}

const TAG_COLOR: Record<Tag, string> = {
  "Good Entry":   "bg-bullish/20 text-bullish border-bullish/30",
  "FOMO":         "bg-bearish/20 text-bearish border-bearish/30",
  "News-Driven":  "bg-blue-500/20 text-blue-400 border-blue-500/30",
  "Revenge Trade":"bg-red-500/20 text-red-400 border-red-500/30",
  "TP Hit":       "bg-green-500/20 text-green-400 border-green-500/30",
  "Stop Hunt":    "bg-orange-500/20 text-orange-400 border-orange-500/30",
  "Oversize":     "bg-purple-500/20 text-purple-400 border-purple-500/30",
};

export function PositionJournalPanel() {
  const [tagMap, dispatch] = useReducer(reducer, undefined, loadTags);

  const { data, isLoading } = useQuery({
    queryKey: ["closed-positions-journal"],
    queryFn: () => fetchClosedPositions({ limit: 30 }),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });

  const positions = data?.positions ?? [];

  const tagStats = useMemo(() => {
    const stats: Record<Tag, { count: number; pnl: number; wins: number }> = {} as never;
    for (const tag of TAGS) stats[tag] = { count: 0, pnl: 0, wins: 0 };
    for (const p of positions) {
      const tags = tagMap[p.id] ?? [];
      for (const t of tags) {
        stats[t].count++;
        stats[t].pnl += p.pnl_pct ?? 0;
        if ((p.pnl_pct ?? 0) > 0) stats[t].wins++;
      }
    }
    return stats;
  }, [positions, tagMap]);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-white">Position Journal</h2>
      <p className="mb-3 text-[10px] text-gray-500">
        Tag trades to identify behavioural patterns. Stats update instantly.
      </p>

      {/* Tag stats summary */}
      <div className="mb-4 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {TAGS.filter((t) => tagStats[t].count > 0).map((t) => {
          const s = tagStats[t];
          const avg = s.count ? s.pnl / s.count : 0;
          return (
            <div key={t} className={`rounded border px-2 py-1.5 text-center text-[10px] ${TAG_COLOR[t]}`}>
              <p className="font-semibold truncate">{t}</p>
              <p className={`font-mono ${colorClass(avg)}`}>{avg >= 0 ? "+" : ""}{avg.toFixed(1)}%</p>
              <p className="text-gray-500">{s.count} trades</p>
            </div>
          );
        })}
      </div>

      {/* Trade list with tag buttons */}
      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse rounded bg-white/5" />)}
        </div>
      ) : (
        <div className="space-y-2 max-h-72 overflow-y-auto">
          {positions.map((p) => {
            const myTags = tagMap[p.id] ?? [];
            return (
              <div key={p.id} className="rounded border border-border bg-background p-2">
                <div className="mb-1.5 flex items-center justify-between text-xs">
                  <span className="font-medium text-gray-200">{p.symbol} {p.direction}</span>
                  <span className={`font-mono font-bold ${colorClass(p.pnl_pct ?? 0)}`}>
                    {fmtPct(p.pnl_pct ?? 0, { showSign: true, decimals: 2 })}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {TAGS.map((tag) => (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => dispatch({ type: "toggle", id: p.id, tag })}
                      className={`rounded border px-1.5 py-0.5 text-[9px] font-medium transition-opacity ${
                        myTags.includes(tag) ? TAG_COLOR[tag] : "border-border bg-background text-gray-600 hover:text-gray-400"
                      }`}
                      aria-pressed={myTags.includes(tag)}
                      aria-label={`Tag ${p.symbol} as ${tag}`}
                    >
                      {tag}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
