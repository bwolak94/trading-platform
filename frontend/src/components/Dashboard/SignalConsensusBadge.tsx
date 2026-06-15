/**
 * Signal Consensus Badge
 * When 3+ strategies agree on direction for the same asset,
 * renders a "CONSENSUS" badge next to the asset name.
 * Exported as a small inline component — used inside SignalCard or signal lists.
 */

import type { Signal } from "../../types";

interface SignalConsensusBadgeProps {
  asset: string;
  direction: "LONG" | "SHORT" | "NEUTRAL";
  allSignals: Signal[];
}

export function SignalConsensusBadge({ asset, direction, allSignals }: SignalConsensusBadgeProps) {
  const matching = allSignals.filter(
    (s) => s.asset === asset && s.direction === direction && s.status === "ACTIVE",
  );

  if (matching.length < 3) return null;

  const color = direction === "LONG"
    ? "bg-bullish/20 text-bullish border-bullish/30"
    : direction === "SHORT"
    ? "bg-bearish/20 text-bearish border-bearish/30"
    : "bg-gray-700 text-gray-400 border-gray-600";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] font-bold ${color}`}
      title={`${matching.length} strategies agree on ${direction}`}
      aria-label={`Consensus: ${matching.length} strategies agree on ${direction} for ${asset}`}
    >
      CONSENSUS {matching.length}x
    </span>
  );
}
