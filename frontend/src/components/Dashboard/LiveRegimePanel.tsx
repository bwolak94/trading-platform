import { useQuery } from "@tanstack/react-query";
import { fetchLiveRegimes, type LiveRegime } from "../../api/client";

// --------------- Config ---------------

const regimeConfig: Record<string, { label: string; color: string; dot: string; badge: string }> = {
  TREND_BULL: {
    label: "TREND BULL",
    color: "text-bullish",
    dot: "bg-bullish",
    badge: "bg-bullish/20 text-bullish",
  },
  TREND_BEAR: {
    label: "TREND BEAR",
    color: "text-bearish",
    dot: "bg-bearish",
    badge: "bg-bearish/20 text-bearish",
  },
  CONSOLIDATION: {
    label: "CONSOLIDATION",
    color: "text-yellow-400",
    dot: "bg-yellow-500",
    badge: "bg-yellow-500/20 text-yellow-400",
  },
  HIGH_VOL_CHOPPY: {
    label: "HIGH VOL",
    color: "text-warning",
    dot: "bg-warning",
    badge: "bg-warning/20 text-warning",
  },
};

function getRegimeConfig(regime: string) {
  return regimeConfig[regime] ?? regimeConfig.CONSOLIDATION!;
}

// --------------- HMM types ---------------

interface HmmRegimeResult {
  asset: string;
  hmm_regime: string;
  hmm_confidence: number;
}

// --------------- HMM section ---------------

interface HmmSectionProps {
  asset: string;
  mainRegime: string;
}

function HmmSection({ asset, mainRegime }: HmmSectionProps) {
  const { data, isLoading } = useQuery<HmmRegimeResult>({
    queryKey: ["hmm-regime", asset],
    queryFn: async () => {
      const res = await fetch(`/api/v1/analytics/hmm-regime?asset=${asset}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json() as Promise<HmmRegimeResult>;
    },
    retry: false,
    staleTime: 60_000,
    refetchInterval: 90_000,
  });

  const hmmRegime = data?.hmm_regime ?? null;
  const hmmConfidence = data?.hmm_confidence ?? 0;
  const hasDivergence = hmmRegime !== null && hmmRegime !== mainRegime;
  const cfg = hmmRegime ? getRegimeConfig(hmmRegime) : null;

  return (
    <div className="mt-3 border-t border-border pt-3">
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs text-gray-400">
          HMM Second Opinion
          <button
            type="button"
            aria-label="What is HMM?"
            title="Hidden Markov Model: a probabilistic model that infers the underlying market regime from price transitions. Acts as a second classifier independent of the rule-based system."
            className="ml-1 inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-gray-600 text-[9px] text-gray-500 hover:border-gray-400 hover:text-gray-300 transition-colors cursor-help"
          >
            ?
          </button>
        </p>
        {hasDivergence && (
          <span
            className="text-xs text-amber-400 flex items-center gap-1"
            role="status"
            aria-label="HMM and main classifier disagree on market regime"
          >
            <span aria-hidden="true">⚠</span> Divergence
          </span>
        )}
      </div>

      {isLoading && (
        <div className="h-4 w-24 animate-pulse rounded bg-border/40" aria-busy="true" aria-label="Loading HMM regime" />
      )}

      {!isLoading && hmmRegime && cfg && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className={`rounded px-2 py-0.5 text-xs font-medium ${cfg.badge}`}>
              {cfg.label}
            </span>
          </div>

          {/* HMM confidence bar */}
          <div>
            <div className="mb-0.5 flex items-center justify-between text-[10px] text-gray-500">
              <span>HMM confidence</span>
              <span className="font-mono">{hmmConfidence.toFixed(0)}%</span>
            </div>
            <div className="h-1 w-full overflow-hidden rounded-full bg-background">
              <div
                className={`h-full rounded-full transition-all ${cfg.dot}`}
                style={{ width: `${Math.min(hmmConfidence, 100)}%` }}
                role="progressbar"
                aria-valuenow={hmmConfidence}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`HMM confidence ${hmmConfidence.toFixed(0)}%`}
              />
            </div>
          </div>
        </div>
      )}

      {!isLoading && !hmmRegime && (
        <p className="text-xs text-gray-600 italic">HMM data unavailable</p>
      )}
    </div>
  );
}

// --------------- LiveRegimePanel ---------------

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
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Fetching live regimes...
        </div>
      )}

      {regimes && regimes.length > 0 && (
        <div className="space-y-3">
          {regimes.map((r: LiveRegime) => {
            const cfg = getRegimeConfig(r.regime);
            return (
              <div key={r.asset} className="rounded bg-background px-3 py-2">
                {/* Main regime row */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className={`h-2 w-2 rounded-full ${cfg.dot}`} aria-hidden="true" />
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

                {/* HMM second opinion */}
                <HmmSection asset={r.asset} mainRegime={r.regime} />
              </div>
            );
          })}
        </div>
      )}

      {regimes?.length === 0 && (
        <p className="text-sm text-gray-500">No regime data available</p>
      )}
    </div>
  );
}
