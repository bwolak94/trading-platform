import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  fetchNotificationHistory,
  fetchNotificationPerformance,
} from "../../api/client";
import type { NotificationRecord } from "../../api/client";

const OUTCOME_CONFIG: Record<string, { label: string; cls: string }> = {
  WIN: { label: "WIN", cls: "bg-green-500/15 text-green-400" },
  LOSS: { label: "LOSS", cls: "bg-red-500/15 text-red-400" },
  PENDING: { label: "PENDING", cls: "bg-yellow-500/15 text-yellow-400" },
  EXPIRED: { label: "EXPIRED", cls: "bg-zinc-500/15 text-zinc-400" },
};

function OutcomeBadge({ outcome }: { outcome: string | null }) {
  const config = OUTCOME_CONFIG[outcome ?? "PENDING"] ?? OUTCOME_CONFIG.PENDING;
  const label = config?.label ?? "PENDING";
  const cls = config?.cls ?? "bg-yellow-500/15 text-yellow-400";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {label}
    </span>
  );
}

function NotificationRow({ notif }: { notif: NotificationRecord }) {
  const [expanded, setExpanded] = useState(false);

  const timeStr = notif.sent_at
    ? new Date(notif.sent_at).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

  const dirIcon = notif.direction === "LONG" ? "▲" : notif.direction === "SHORT" ? "▼" : "●";
  const dirColor = notif.direction === "LONG" ? "text-green-400" : notif.direction === "SHORT" ? "text-red-400" : "text-muted-foreground";

  return (
    <div className="rounded-md border border-border/50 bg-surface/50">
      <button
        onClick={() => { setExpanded((v) => !v); }}
        className="grid w-full grid-cols-[1fr_auto_auto_auto_auto] items-center gap-3 px-3 py-2 text-left text-sm"
        aria-expanded={expanded}
        aria-label={`Toggle details for ${notif.asset} signal`}
      >
        <div className="min-w-0">
          <span className="font-semibold text-foreground">
            {notif.asset ?? notif.message_type}
          </span>
          {notif.strategy && (
            <span className="ml-1.5 text-xs text-muted-foreground">{notif.strategy}</span>
          )}
        </div>
        <span className={`font-mono text-xs ${dirColor}`}>
          {dirIcon} {notif.direction ?? "—"}
        </span>
        {notif.confidence !== null && (
          <span className="text-xs text-muted-foreground">{notif.confidence}%</span>
        )}
        <OutcomeBadge outcome={notif.outcome} />
        <span className="text-xs text-muted-foreground">{timeStr}</span>
      </button>

      {expanded && (
        <div className="border-t border-border/50 px-3 py-2">
          {notif.entry_price !== null && (
            <div className="mb-1 grid grid-cols-3 gap-2 text-xs text-muted-foreground">
              <span>Entry: <span className="text-foreground">{notif.entry_price?.toFixed(4)}</span></span>
              <span>SL: <span className="text-red-400">{notif.stop_loss?.toFixed(4)}</span></span>
              <span>TP1: <span className="text-green-400">{notif.take_profit_1?.toFixed(4)}</span></span>
            </div>
          )}
          {notif.pnl_pct !== null && (
            <p className="text-xs text-muted-foreground">
              PnL:{" "}
              <span className={notif.pnl_pct >= 0 ? "text-green-400" : "text-red-400"}>
                {notif.pnl_pct >= 0 ? "+" : ""}{notif.pnl_pct.toFixed(2)}%
              </span>
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function PerformanceSummary() {
  const { data } = useQuery({
    queryKey: ["notif-performance"],
    queryFn: fetchNotificationPerformance,
    refetchInterval: 60_000,
  });

  if (!data) return null;

  const winPct = (data.win_rate * 100).toFixed(1);
  const wins = data.breakdown.WIN?.count ?? 0;
  const losses = data.breakdown.LOSS?.count ?? 0;
  const pending = data.breakdown.PENDING?.count ?? 0;

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border/50 bg-surface/50 px-3 py-2 text-xs">
      <span className="text-muted-foreground">
        Total: <span className="font-medium text-foreground">{data.total_signals}</span>
      </span>
      <span className="text-muted-foreground">
        Win rate: <span className={`font-medium ${data.win_rate >= 0.5 ? "text-green-400" : "text-red-400"}`}>{winPct}%</span>
      </span>
      <span className="text-green-400">{wins}W</span>
      <span className="text-red-400">{losses}L</span>
      <span className="text-yellow-400">{pending} pending</span>
    </div>
  );
}

export function NotificationHistoryPanel() {
  const [page, setPage] = useState(0);
  const limit = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["notif-history", page],
    queryFn: () => fetchNotificationHistory({ limit, offset: page * limit }),
    refetchInterval: 30_000,
  });

  const notifications = data?.notifications ?? [];
  const total = data?.total ?? 0;
  const hasNext = (page + 1) * limit < total;
  const hasPrev = page > 0;

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">Notification History</h2>
        <p className="text-xs text-muted-foreground">All Telegram signals sent with trade outcomes</p>
      </div>

      <PerformanceSummary />

      {isLoading ? (
        <div className="flex h-24 items-center justify-center text-sm text-muted-foreground">
          Loading...
        </div>
      ) : notifications.length === 0 ? (
        <div className="flex h-24 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
          No notifications yet
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {notifications.map((n) => (
            <NotificationRow key={n.id} notif={n} />
          ))}
        </div>
      )}

      {total > limit && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {page * limit + 1}–{Math.min((page + 1) * limit, total)} of {total}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => { setPage((p) => p - 1); }}
              disabled={!hasPrev}
              className="rounded px-2 py-1 hover:bg-surface disabled:opacity-40"
              aria-label="Previous page"
            >
              ← Prev
            </button>
            <button
              onClick={() => { setPage((p) => p + 1); }}
              disabled={!hasNext}
              className="rounded px-2 py-1 hover:bg-surface disabled:opacity-40"
              aria-label="Next page"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
