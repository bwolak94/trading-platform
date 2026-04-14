import { useQuery } from "@tanstack/react-query";
import { fetchLiveRegimes, type LiveRegime } from "../../api/client";

const regimeConfig: Record<string, { label: string; color: string; dot: string }> = {
  TREND_BULL: { label: "TREND BULL", color: "text-bullish", dot: "bg-bullish" },
  TREND_BEAR: { label: "TREND BEAR", color: "text-bearish", dot: "bg-bearish" },
  CONSOLIDATION: { label: "CONSOLIDATION", color: "text-yellow-400", dot: "bg-yellow-500" },
  HIGH_VOL_CHOPPY: { label: "HIGH VOL", color: "text-warning", dot: "bg-warning" },
};

export function LiveRegimePanel() {
  const { data: regimes, isLoading } = useQuery({
    queryKey: ["liveRegimes"],
    queryFn: fetchLiveRegimes,
    refetchInterval: 60_000,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-gray-500">
        Market Regimes (Live)
      </h2>

      {isLoading && (
        <div className="flex items-center gap-2 py-4 text-sm text-gray-400">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Fetching live regimes...
        </div>
      )}

      {regimes && regimes.length > 0 && (
        <div className="space-y-2">
          {regimes.map((r: LiveRegime) => {
            const cfg = regimeConfig[r.regime] ?? regimeConfig["CONSOLIDATION"]!;
            return (
              <div key={r.asset} className="flex items-center justify-between rounded bg-background px-3 py-2">
                <div className="flex items-center gap-2">
                  <div className={`h-2 w-2 rounded-full ${cfg.dot}`} />
                  <span className="font-mono text-sm text-white">{r.asset}</span>
                  <span className="font-mono text-xs text-gray-400">${r.price.toLocaleString()}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`text-xs font-medium ${cfg.color}`}>{cfg.label}</span>
                  <span className="font-mono text-xs text-gray-400">{r.confidence.toFixed(0)}%</span>
                  <div className="flex gap-2 text-xs text-gray-500">
                    <span>RSI {r.rsi}</span>
                    <span>ADX {r.adx}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {regimes && regimes.length === 0 && (
        <p className="text-sm text-gray-500">No regime data available</p>
      )}
    </div>
  );
}
