interface RiskPanelProps {
  systemStatus: "ACTIVE" | "PAUSED";
  drawdownPct: number;
  maxDrawdownPct: number;
  onResetKillSwitch?: () => void;
}

export function RiskPanel({
  systemStatus,
  drawdownPct,
  maxDrawdownPct,
  onResetKillSwitch,
}: RiskPanelProps) {
  const isPaused = systemStatus === "PAUSED";
  const drawdownRatio = maxDrawdownPct > 0 ? drawdownPct / maxDrawdownPct : 0;
  const gaugeColor =
    drawdownRatio > 0.8 ? "bg-bearish" : drawdownRatio > 0.5 ? "bg-warning" : "bg-bullish";

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-gray-500">
        Risk Monitor
      </h2>

      {/* System Status */}
      <div className="mb-4 flex items-center justify-between">
        <span className="text-sm text-gray-400">System</span>
        <span
          className={`rounded px-2 py-0.5 text-xs font-bold ${
            isPaused
              ? "bg-bearish/20 text-bearish"
              : "bg-bullish/20 text-bullish"
          }`}
        >
          {systemStatus}
        </span>
      </div>

      {/* Drawdown Gauge */}
      <div className="mb-2">
        <div className="mb-1 flex justify-between text-sm">
          <span className="text-gray-400">Drawdown</span>
          <span className="font-mono text-white">
            {drawdownPct.toFixed(1)}% / {maxDrawdownPct.toFixed(0)}%
          </span>
        </div>
        <div className="h-3 w-full overflow-hidden rounded-full bg-background">
          <div
            className={`h-full rounded-full transition-all ${gaugeColor}`}
            style={{ width: `${Math.min(drawdownRatio * 100, 100)}%` }}
          />
        </div>
      </div>

      {/* Kill switch warning */}
      {isPaused && (
        <div className="mt-4 rounded border border-bearish/30 bg-bearish/10 p-3">
          <p className="mb-2 text-sm text-bearish">
            System paused — drawdown limit reached
          </p>
          {onResetKillSwitch && (
            <button
              onClick={onResetKillSwitch}
              className="rounded bg-bearish px-3 py-1 text-xs font-medium text-white hover:bg-bearish/80"
              aria-label="Reset kill switch and resume system"
            >
              Reset & Resume
            </button>
          )}
        </div>
      )}
    </div>
  );
}
