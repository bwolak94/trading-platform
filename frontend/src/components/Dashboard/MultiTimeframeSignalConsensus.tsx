/**
 * B13: Multi-Timeframe Signal Consensus
 *
 * Shows signal direction on 1h/4h/1D timeframes for the selected asset.
 * Green if all aligned, amber if mixed, red if opposing.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

interface TFSignal {
  timeframe: string;
  direction: "LONG" | "SHORT" | "NEUTRAL" | null;
  confidence: number;
}

interface ConsensusData {
  asset: string;
  consensus: "ALIGNED_LONG" | "ALIGNED_SHORT" | "MIXED" | "NEUTRAL";
  signals: TFSignal[];
}

async function fetchConsensus(symbol: string): Promise<ConsensusData> {
  const resp = await fetch(`/api/v1/signals/mtf-consensus?symbol=${encodeURIComponent(symbol)}`);
  if (!resp.ok) throw new Error("Failed to fetch MTF consensus");
  return resp.json();
}

const DIRECTION_STYLES: Record<string, string> = {
  LONG: "border-bullish/40 bg-bullish/10 text-bullish",
  SHORT: "border-bearish/40 bg-bearish/10 text-bearish",
  NEUTRAL: "border-gray-600 bg-gray-800 text-gray-400",
};

const CONSENSUS_BADGE: Record<string, { label: string; cls: string }> = {
  ALIGNED_LONG: { label: "All Long", cls: "bg-bullish/20 text-bullish" },
  ALIGNED_SHORT: { label: "All Short", cls: "bg-bearish/20 text-bearish" },
  MIXED: { label: "Mixed", cls: "bg-amber-500/20 text-amber-400" },
  NEUTRAL: { label: "Neutral", cls: "bg-gray-700 text-gray-400" },
};

export function MultiTimeframeSignalConsensus() {
  const [symbol, setSymbol] = useState("BTC/USDT");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["mtf-consensus", symbol],
    queryFn: () => fetchConsensus(symbol),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  const badge = data ? CONSENSUS_BADGE[data.consensus] : null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">MTF Signal Consensus</h3>
          <p className="text-xs text-gray-400">1h / 4h / 1D alignment check</p>
        </div>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300"
          aria-label="Select asset for MTF consensus"
        >
          <option value="BTC/USDT">BTC/USDT</option>
          <option value="ETH/USDT">ETH/USDT</option>
          <option value="SOL/USDT">SOL/USDT</option>
          <option value="BNB/USDT">BNB/USDT</option>
        </select>
      </div>

      {isLoading && (
        <div className="flex h-28 items-center justify-center text-xs text-gray-500">Loading…</div>
      )}
      {isError && (
        <div className="flex h-28 items-center justify-center text-xs text-bearish">
          Failed to load MTF data
        </div>
      )}

      {!isLoading && !isError && data && (
        <div>
          {badge && (
            <div className={`mb-3 inline-flex rounded px-2 py-1 text-xs font-semibold ${badge.cls}`}>
              {badge.label}
            </div>
          )}
          <div className="grid grid-cols-3 gap-2">
            {data.signals.map((sig) => (
              <div
                key={sig.timeframe}
                className={`rounded border p-3 text-center ${DIRECTION_STYLES[sig.direction ?? "NEUTRAL"]}`}
              >
                <div className="mb-1 text-xs font-medium text-gray-400">{sig.timeframe}</div>
                <div className="text-sm font-bold">{sig.direction ?? "—"}</div>
                {sig.confidence > 0 && (
                  <div className="mt-1 text-[10px] opacity-70">{sig.confidence.toFixed(0)}%</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
