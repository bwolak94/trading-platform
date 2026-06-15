/**
 * Sentiment vs Price Divergence Detector
 * Flags when price action contradicts FinBERT/aggregated sentiment.
 * Bullish price + bearish sentiment = potential reversal zone (over-extended up).
 * Bearish price + bullish sentiment = potential reversal zone (over-extended down).
 */

import { useQuery } from "@tanstack/react-query";
import { fetchSentimentSnapshot, fetchLiveRegimes } from "../../api/client";
import { fmtPct } from "../../lib/format";

type DivergenceType =
  | "bull_price_bear_sent"   // Price up, sentiment down → potential top
  | "bear_price_bull_sent"   // Price down, sentiment up → potential bottom
  | "aligned_bull"            // Both positive
  | "aligned_bear"            // Both negative
  | "neutral";

interface DivergenceSignal {
  asset: string;
  regime: string;
  confidence: number;
  sentimentScore: number;
  divergence: DivergenceType;
  strength: number;           // 0–100
}

const DIVERGENCE_META: Record<DivergenceType, { label: string; color: string; bg: string; icon: string }> = {
  bull_price_bear_sent: {
    label: "Potential Top",
    color: "text-amber-400",
    bg: "bg-amber-400/10 border-amber-400/30",
    icon: "⚠️",
  },
  bear_price_bull_sent: {
    label: "Potential Bottom",
    color: "text-blue-400",
    bg: "bg-blue-400/10 border-blue-400/30",
    icon: "🔄",
  },
  aligned_bull: {
    label: "Aligned Bullish",
    color: "text-bullish",
    bg: "bg-bullish/5 border-bullish/20",
    icon: "✓",
  },
  aligned_bear: {
    label: "Aligned Bearish",
    color: "text-bearish",
    bg: "bg-bearish/5 border-bearish/20",
    icon: "✓",
  },
  neutral: {
    label: "Neutral",
    color: "text-gray-400",
    bg: "bg-background border-border",
    icon: "—",
  },
};

function classify(regime: string, sentiment: number): DivergenceType {
  const priceUp = regime.includes("BULL");
  const priceDown = regime.includes("BEAR");
  const sentBull = sentiment > 0.15;
  const sentBear = sentiment < -0.15;

  if (priceUp && sentBear) return "bull_price_bear_sent";
  if (priceDown && sentBull) return "bear_price_bull_sent";
  if (priceUp && sentBull) return "aligned_bull";
  if (priceDown && sentBear) return "aligned_bear";
  return "neutral";
}

export function SentimentDivergencePanel() {
  const sentQ = useQuery({
    queryKey: ["sentiment-snapshot-div"],
    queryFn: fetchSentimentSnapshot,
    refetchInterval: 60_000,
    retry: false,
  });

  const regimeQ = useQuery({
    queryKey: ["live-regimes-div"],
    queryFn: fetchLiveRegimes,
    refetchInterval: 60_000,
    retry: false,
  });

  const isLoading = sentQ.isLoading || regimeQ.isLoading;
  const isError = sentQ.isError || regimeQ.isError;

  const signals: DivergenceSignal[] = (regimeQ.data ?? []).map((r) => {
    const sentiment = sentQ.data?.global_sentiment ?? 0;
    const div = classify(r.regime, sentiment);
    const strength = Math.round(
      Math.abs(r.confidence) * 50 + Math.min(Math.abs(sentiment) * 200, 50),
    );
    return {
      asset: r.asset,
      regime: r.regime,
      confidence: r.confidence,
      sentimentScore: sentiment,
      divergence: div,
      strength: Math.min(strength, 100),
    };
  });

  // Sort: divergences first, then by strength
  const sorted = [...signals].sort((a, b) => {
    const aDiv = a.divergence.startsWith("bull_price") || a.divergence.startsWith("bear_price") ? 1 : 0;
    const bDiv = b.divergence.startsWith("bull_price") || b.divergence.startsWith("bear_price") ? 1 : 0;
    if (aDiv !== bDiv) return bDiv - aDiv;
    return b.strength - a.strength;
  });

  const divergentCount = sorted.filter(
    (s) => s.divergence === "bull_price_bear_sent" || s.divergence === "bear_price_bull_sent",
  ).length;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Sentiment Divergence</h2>
        {divergentCount > 0 && (
          <span className="rounded bg-amber-400/20 px-2 py-0.5 text-xs font-bold text-amber-400">
            {divergentCount} divergent
          </span>
        )}
      </div>

      <p className="mb-3 text-[10px] text-gray-500">
        Compares live price regime vs aggregated news sentiment. Divergence may signal reversal risk.
      </p>

      {isError && <p className="mb-2 text-xs text-bearish">Data unavailable</p>}

      {/* Global sentiment bar */}
      {sentQ.data && (
        <div className="mb-4 rounded bg-background px-3 py-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">Global Sentiment</span>
            <span className={sentQ.data.global_sentiment >= 0 ? "text-bullish" : "text-bearish"}>
              {fmtPct(sentQ.data.global_sentiment * 100, { showSign: true, decimals: 1 })}
            </span>
          </div>
          <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
            <div
              className={`h-full rounded-full ${sentQ.data.global_sentiment >= 0 ? "bg-bullish" : "bg-bearish"}`}
              style={{ width: `${Math.abs(sentQ.data.global_sentiment) * 100}%`, marginLeft: sentQ.data.global_sentiment >= 0 ? "50%" : `${50 - Math.abs(sentQ.data.global_sentiment) * 50}%` }}
            />
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-white/5" />
          ))}
        </div>
      ) : (
        <div className="space-y-1.5">
          {sorted.slice(0, 6).map((sig) => {
            const meta = DIVERGENCE_META[sig.divergence];
            return (
              <div
                key={sig.asset}
                className={`flex items-center justify-between rounded border px-3 py-2 text-xs ${meta.bg}`}
                role="listitem"
              >
                <div className="flex items-center gap-2">
                  <span className="text-base" aria-hidden="true">{meta.icon}</span>
                  <div>
                    <span className="font-medium text-gray-200">
                      {sig.asset.replace("USDT", "")}
                    </span>
                    <span className="ml-1.5 text-gray-500">{sig.regime.replace("_", " ")}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] font-medium ${meta.color}`}>
                    {meta.label}
                  </span>
                  <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-gray-400">
                    {sig.strength}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
