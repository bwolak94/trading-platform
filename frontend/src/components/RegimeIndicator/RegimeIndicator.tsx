import type { RegimeData } from "../../types";

const regimeConfig = {
  TREND_BULL: { label: "TREND BULL", color: "bg-bullish", text: "text-bullish", dot: "bg-bullish" },
  TREND_BEAR: { label: "TREND BEAR", color: "bg-bearish", text: "text-bearish", dot: "bg-bearish" },
  CONSOLIDATION: { label: "CONSOLIDATION", color: "bg-yellow-500", text: "text-yellow-400", dot: "bg-yellow-500" },
  HIGH_VOL_CHOPPY: { label: "HIGH VOL", color: "bg-warning", text: "text-warning", dot: "bg-warning" },
} as const;

interface RegimePanelProps {
  regimes: RegimeData[];
}

export function RegimePanel({ regimes }: RegimePanelProps) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-gray-500">
        Market Regimes
      </h2>
      <div className="space-y-2">
        {regimes.length === 0 && (
          <p className="text-sm text-gray-500">No regime data available</p>
        )}
        {regimes.map((regime) => {
          const cfg = regimeConfig[regime.regime] ?? regimeConfig.CONSOLIDATION;
          const duration = regime.started_at
            ? formatDuration(new Date(regime.started_at))
            : "";

          return (
            <div
              key={regime.asset}
              className="flex items-center justify-between rounded bg-background px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <div className={`h-2 w-2 rounded-full ${cfg.dot}`} />
                <span className="font-mono text-sm text-white">
                  {regime.asset}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className={`rounded px-2 py-0.5 text-xs font-medium ${cfg.color}/20 ${cfg.text}`}
                >
                  {cfg.label}
                </span>
                <span className="font-mono text-xs text-gray-400">
                  {regime.confidence.toFixed(0)}%
                </span>
                {duration && (
                  <span className="text-xs text-gray-600">{duration}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatDuration(since: Date): string {
  const diff = Date.now() - since.getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return "<1h";
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}
