import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { fetchAgentStatus, fetchDayTradeStatus } from "../api/client";

interface Trade {
  time: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  strategy: string;
  entry: number;
  exit: number;
  pnl_pct: number;
  hit_level: string;
  reward: number;
  source: "swing" | "day";
}

function formatNumber(n: number): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

function formatTime(iso: string): string {
  if (!iso) return "N/A";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

type FilterResult = "all" | "win" | "loss";

export function TradeHistoryPage() {
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

  const [filterSymbol, setFilterSymbol] = useState<string>("all");
  const [filterStrategy, setFilterStrategy] = useState<string>("all");
  const [filterResult, setFilterResult] = useState<FilterResult>("all");

  // Combine trades from both agents
  const allTrades: Trade[] = useMemo(() => {
    const trades: Trade[] = [];

    const swingTrades = (swingStatus as unknown as Record<string, unknown>)?.recent_trades;
    if (Array.isArray(swingTrades)) {
      for (const t of swingTrades) {
        const trade = t as Record<string, unknown>;
        trades.push({
          time: String(trade.timestamp ?? trade.time ?? ""),
          symbol: String(trade.symbol ?? ""),
          direction: (trade.direction ?? trade.action ?? "LONG") as "LONG" | "SHORT",
          strategy: String(trade.strategy ?? trade.strategy_name ?? "Swing"),
          entry: Number(trade.entry ?? 0),
          exit: Number(trade.exit ?? trade.exit_price ?? 0),
          pnl_pct: Number(trade.pnl_pct ?? trade.pnl ?? 0),
          hit_level: String(trade.hit_level ?? trade.exit_reason ?? "N/A"),
          reward: Number(trade.reward ?? 0),
          source: "swing",
        });
      }
    }

    const dayTrades = (dayStatus as unknown as Record<string, unknown>)?.recent_trades;
    if (Array.isArray(dayTrades)) {
      for (const t of dayTrades) {
        const trade = t as Record<string, unknown>;
        trades.push({
          time: String(trade.timestamp ?? trade.time ?? ""),
          symbol: String(trade.symbol ?? ""),
          direction: (trade.direction ?? trade.action ?? "LONG") as "LONG" | "SHORT",
          strategy: String(trade.strategy ?? trade.strategy_type ?? "DayTrade"),
          entry: Number(trade.entry ?? 0),
          exit: Number(trade.exit ?? trade.exit_price ?? 0),
          pnl_pct: Number(trade.pnl_pct ?? trade.pnl ?? 0),
          hit_level: String(trade.hit_level ?? trade.exit_reason ?? "N/A"),
          reward: Number(trade.reward ?? 0),
          source: "day",
        });
      }
    }

    // Sort by timestamp descending
    trades.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime());
    return trades;
  }, [swingStatus, dayStatus]);

  // Derive unique symbols and strategies for filter dropdowns
  const symbols = useMemo(() => [...new Set(allTrades.map((t) => t.symbol))].sort(), [allTrades]);
  const strategies = useMemo(() => [...new Set(allTrades.map((t) => t.strategy))].sort(), [allTrades]);

  // Apply filters
  const filteredTrades = useMemo(() => {
    return allTrades.filter((t) => {
      if (filterSymbol !== "all" && t.symbol !== filterSymbol) return false;
      if (filterStrategy !== "all" && t.strategy !== filterStrategy) return false;
      if (filterResult === "win" && t.pnl_pct <= 0) return false;
      if (filterResult === "loss" && t.pnl_pct >= 0) return false;
      return true;
    });
  }, [allTrades, filterSymbol, filterStrategy, filterResult]);

  // Summary stats
  const stats = useMemo(() => {
    if (filteredTrades.length === 0) {
      return { total: 0, wins: 0, winRate: 0, totalPnl: 0, best: 0, worst: 0, avgReward: 0 };
    }
    const wins = filteredTrades.filter((t) => t.pnl_pct > 0).length;
    const totalPnl = filteredTrades.reduce((sum, t) => sum + t.pnl_pct, 0);
    const pnls = filteredTrades.map((t) => t.pnl_pct);
    const rewards = filteredTrades.map((t) => t.reward);
    return {
      total: filteredTrades.length,
      wins,
      winRate: (wins / filteredTrades.length) * 100,
      totalPnl,
      best: Math.max(...pnls),
      worst: Math.min(...pnls),
      avgReward: rewards.reduce((s, r) => s + r, 0) / rewards.length,
    };
  }, [filteredTrades]);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-white">Trade History</h1>

      {/* Summary Stats */}
      <div
        className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-7"
        aria-label="Trade history summary statistics"
      >
        {[
          { label: "Total Trades", value: String(stats.total) },
          { label: "Wins", value: String(stats.wins) },
          { label: "Win Rate", value: `${stats.winRate.toFixed(1)}%` },
          { label: "Total P&L", value: `${stats.totalPnl >= 0 ? "+" : ""}${stats.totalPnl.toFixed(2)}%` },
          { label: "Best Trade", value: `${stats.best >= 0 ? "+" : ""}${stats.best.toFixed(2)}%` },
          { label: "Worst Trade", value: `${stats.worst >= 0 ? "+" : ""}${stats.worst.toFixed(2)}%` },
          { label: "Avg Reward", value: `${stats.avgReward >= 0 ? "+" : ""}${stats.avgReward.toFixed(2)}R` },
        ].map((s) => (
          <div
            key={s.label}
            className="rounded-lg border border-border bg-surface p-3 text-center"
          >
            <div className="text-lg font-bold text-white">{s.value}</div>
            <div className="text-[11px] text-gray-400">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3" aria-label="Trade history filters">
        <div>
          <label htmlFor="filter-symbol" className="mr-1 text-xs text-gray-500">
            Symbol
          </label>
          <select
            id="filter-symbol"
            value={filterSymbol}
            onChange={(e) => setFilterSymbol(e.target.value)}
            className="rounded border border-border bg-surface px-2 py-1 text-sm text-white"
            aria-label="Filter by symbol"
          >
            <option value="all">All Symbols</option>
            {symbols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="filter-strategy" className="mr-1 text-xs text-gray-500">
            Strategy
          </label>
          <select
            id="filter-strategy"
            value={filterStrategy}
            onChange={(e) => setFilterStrategy(e.target.value)}
            className="rounded border border-border bg-surface px-2 py-1 text-sm text-white"
            aria-label="Filter by strategy"
          >
            <option value="all">All Strategies</option>
            {strategies.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="filter-result" className="mr-1 text-xs text-gray-500">
            Result
          </label>
          <select
            id="filter-result"
            value={filterResult}
            onChange={(e) => setFilterResult(e.target.value as FilterResult)}
            className="rounded border border-border bg-surface px-2 py-1 text-sm text-white"
            aria-label="Filter by result"
          >
            <option value="all">All</option>
            <option value="win">Wins</option>
            <option value="loss">Losses</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div
        className="overflow-x-auto rounded-lg border border-border bg-surface"
        aria-label="Trade history table"
      >
        {filteredTrades.length === 0 ? (
          <div className="p-8 text-center text-sm text-gray-500">
            No trades found. Trades will appear here after the AI agent closes positions.
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border text-xs text-gray-500">
              <tr>
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Symbol</th>
                <th className="px-4 py-3">Direction</th>
                <th className="px-4 py-3">Strategy</th>
                <th className="px-4 py-3 text-right">Entry</th>
                <th className="px-4 py-3 text-right">Exit</th>
                <th className="px-4 py-3 text-right">P&L%</th>
                <th className="px-4 py-3">Hit Level</th>
                <th className="px-4 py-3 text-right">Reward</th>
                <th className="px-4 py-3">Source</th>
              </tr>
            </thead>
            <tbody>
              {filteredTrades.map((trade, i) => {
                const isWin = trade.pnl_pct > 0;
                const rowBg = isWin
                  ? "bg-green-900/10 hover:bg-green-900/20"
                  : trade.pnl_pct < 0
                    ? "bg-red-900/10 hover:bg-red-900/20"
                    : "hover:bg-surface/80";
                return (
                  <tr
                    key={`${trade.time}-${trade.symbol}-${i}`}
                    className={`border-b border-border transition-colors ${rowBg}`}
                  >
                    <td className="whitespace-nowrap px-4 py-2 text-gray-300">
                      {formatTime(trade.time)}
                    </td>
                    <td className="px-4 py-2 font-mono text-white">{trade.symbol}</td>
                    <td className="px-4 py-2">
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-semibold text-white ${
                          trade.direction === "LONG" ? "bg-green-600" : "bg-red-600"
                        }`}
                      >
                        {trade.direction}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-gray-400">{trade.strategy}</td>
                    <td className="px-4 py-2 text-right font-mono text-white">
                      ${formatNumber(trade.entry)}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-white">
                      ${formatNumber(trade.exit)}
                    </td>
                    <td
                      className={`px-4 py-2 text-right font-mono font-semibold ${
                        isWin ? "text-green-400" : trade.pnl_pct < 0 ? "text-red-400" : "text-gray-400"
                      }`}
                    >
                      {trade.pnl_pct >= 0 ? "+" : ""}
                      {trade.pnl_pct.toFixed(2)}%
                    </td>
                    <td className="px-4 py-2 text-gray-400">{trade.hit_level}</td>
                    <td
                      className={`px-4 py-2 text-right font-mono ${
                        trade.reward >= 0 ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {trade.reward >= 0 ? "+" : ""}
                      {trade.reward.toFixed(2)}R
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] font-medium ${
                          trade.source === "swing"
                            ? "bg-purple-900/50 text-purple-300"
                            : "bg-blue-900/50 text-blue-300"
                        }`}
                      >
                        {trade.source === "swing" ? "Swing" : "Day"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
