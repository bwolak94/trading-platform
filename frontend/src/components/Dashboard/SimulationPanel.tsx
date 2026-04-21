import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchOpenPositions,
  fetchClosedPositions,
  fetchSimulationStatus,
  startSimulation,
  stopSimulation,
} from "../../api/client";
import type { SimulatedPosition } from "../../api/client";

function DirectionBadge({ direction }: { direction: "LONG" | "SHORT" }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
        direction === "LONG"
          ? "bg-green-500/15 text-green-400"
          : "bg-red-500/15 text-red-400"
      }`}
    >
      {direction === "LONG" ? "▲" : "▼"} {direction}
    </span>
  );
}

function PnlBadge({ pnl }: { pnl: number }) {
  const isPositive = pnl >= 0;
  return (
    <span
      className={`font-mono text-sm font-semibold ${isPositive ? "text-green-400" : "text-red-400"}`}
    >
      {isPositive ? "+" : ""}
      {pnl.toFixed(2)}%
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    OPEN: "bg-blue-500/15 text-blue-400",
    CLOSED: "bg-zinc-500/15 text-zinc-400",
    STOPPED_OUT: "bg-red-500/15 text-red-400",
    TP1_HIT: "bg-green-500/15 text-green-400",
    TP2_HIT: "bg-emerald-500/15 text-emerald-400",
    TP3_HIT: "bg-teal-500/15 text-teal-400",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        colorMap[status] ?? "bg-zinc-500/15 text-zinc-400"
      }`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

function PositionRow({
  pos,
  onSelect,
}: {
  pos: SimulatedPosition;
  onSelect?: (pos: SimulatedPosition) => void;
}) {
  const timeStr = new Date(pos.opened_at).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <button
      type="button"
      onClick={() => onSelect?.(pos)}
      className="grid w-full grid-cols-[1fr_auto_auto_auto_auto_auto] items-center gap-3 rounded-md border border-border/50 bg-surface/50 px-3 py-2 text-left text-sm transition-colors hover:border-accent/50 hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      aria-label={`View details for ${pos.symbol} ${pos.direction} position`}
    >
      <div>
        <span className="font-semibold text-foreground">{pos.symbol}</span>
        <span className="ml-1 text-xs text-muted-foreground">{pos.strategy.replace(/_/g, " ")}</span>
      </div>
      <DirectionBadge direction={pos.direction as "LONG" | "SHORT"} />
      <span className="font-mono text-muted-foreground">{pos.entry_price.toFixed(4)}</span>
      <PnlBadge pnl={pos.pnl_pct} />
      <StatusBadge status={pos.status} />
      <span className="text-xs text-muted-foreground">{timeStr}</span>
    </button>
  );
}

function EngineControls() {
  const queryClient = useQueryClient();

  const { data: status } = useQuery({
    queryKey: ["sim-status"],
    queryFn: fetchSimulationStatus,
    refetchInterval: 10_000,
  });

  const startMut = useMutation({
    mutationFn: startSimulation,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sim-status"] }),
  });

  const stopMut = useMutation({
    mutationFn: stopSimulation,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sim-status"] }),
  });

  const running = status?.is_running ?? false;
  const busy = startMut.isPending || stopMut.isPending;

  return (
    <div className="flex items-center gap-3">
      <span
        className={`inline-block h-2.5 w-2.5 rounded-full ${
          running
            ? "bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.6)]"
            : "bg-zinc-500"
        }`}
        aria-hidden="true"
      />
      <span className="text-sm text-muted-foreground">
        {running ? "Running" : "Stopped"}
      </span>
      <button
        onClick={() => (running ? stopMut.mutate() : startMut.mutate())}
        disabled={busy}
        className={`rounded-md px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
          running
            ? "bg-red-500/15 text-red-400 hover:bg-red-500/25"
            : "bg-green-500/15 text-green-400 hover:bg-green-500/25"
        }`}
        aria-label={running ? "Stop simulation" : "Start simulation"}
      >
        {busy ? "..." : running ? "Stop" : "Start"}
      </button>
      {status && (
        <span className="text-xs text-muted-foreground">
          {status.open_positions}/{status.max_positions} positions
        </span>
      )}
    </div>
  );
}

interface SimulationPanelProps {
  onPositionClick?: (pos: SimulatedPosition) => void;
}

export function SimulationPanel({ onPositionClick }: SimulationPanelProps) {
  const { data: openData, isLoading: openLoading } = useQuery({
    queryKey: ["sim-open-positions"],
    queryFn: fetchOpenPositions,
    refetchInterval: 5_000,
  });

  const { data: closedData, isLoading: closedLoading } = useQuery({
    queryKey: ["sim-closed-positions"],
    queryFn: () => fetchClosedPositions({ limit: 10 }),
    refetchInterval: 30_000,
  });

  const openPositions = openData?.positions ?? [];
  const closedPositions = closedData?.positions ?? [];

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-foreground">
            Paper Trading Simulation
          </h2>
          <p className="text-xs text-muted-foreground">
            24/7 automated bot — virtual positions only
          </p>
        </div>
        <EngineControls />
      </div>

      {/* Open Positions */}
      <section aria-labelledby="open-pos-heading">
        <h3
          id="open-pos-heading"
          className="mb-2 text-sm font-medium text-muted-foreground"
        >
          Open Positions{" "}
          <span className="ml-1 rounded-full bg-blue-500/15 px-1.5 py-0.5 text-xs text-blue-400">
            {openPositions.length}
          </span>
        </h3>

        {openLoading ? (
          <div className="flex h-16 items-center justify-center text-sm text-muted-foreground">
            Loading...
          </div>
        ) : openPositions.length === 0 ? (
          <div className="flex h-16 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
            No open positions
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {openPositions.map((pos) => (
              <PositionRow key={pos.id} pos={pos} onSelect={onPositionClick} />
            ))}
          </div>
        )}
      </section>

      {/* Recent Closed */}
      <section aria-labelledby="closed-pos-heading">
        <h3
          id="closed-pos-heading"
          className="mb-2 text-sm font-medium text-muted-foreground"
        >
          Recent Closed
        </h3>

        {closedLoading ? (
          <div className="flex h-16 items-center justify-center text-sm text-muted-foreground">
            Loading...
          </div>
        ) : closedPositions.length === 0 ? (
          <div className="flex h-16 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
            No closed positions yet
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {closedPositions.map((pos) => (
              <PositionRow key={pos.id} pos={pos} onSelect={onPositionClick} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
