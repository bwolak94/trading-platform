import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { PriceChart } from "./PriceChart";
import { fetchAgentSignals, fetchDayTradeSignals } from "../../api/client";
// AgentSignal and DayTradeSignal types are used via fetchAgentSignals/fetchDayTradeSignals return types

type LayoutMode = "1" | "2h" | "2v" | "3" | "4";

// Layout button configs
const LAYOUTS: { mode: LayoutMode; label: string; icon: string }[] = [
  { mode: "1", label: "Single", icon: "\u25A1" },
  { mode: "2h", label: "2 Horizontal", icon: "\u25AB\u25AB" },
  { mode: "2v", label: "2 Vertical", icon: "\u25AA\n\u25AA" },
  { mode: "3", label: "3 Charts", icon: "\u25AB\u25AB\n\u25AB" },
  { mode: "4", label: "4 Charts", icon: "\u25AB\u25AB\n\u25AB\u25AB" },
];

function getGridClass(mode: LayoutMode): string {
  switch (mode) {
    case "1": return "grid-cols-1";
    case "2h": return "grid-cols-2";
    case "2v": return "grid-cols-1";
    case "3": return "grid-cols-2";
    case "4": return "grid-cols-2";
    default: return "grid-cols-1";
  }
}

function getChartCount(mode: LayoutMode): number {
  switch (mode) {
    case "1": return 1;
    case "2h": return 2;
    case "2v": return 2;
    case "3": return 3;
    case "4": return 4;
    default: return 1;
  }
}

export function MultiChart({ onAssetChange }: { onAssetChange?: (asset: string, tf: string) => void }) {
  const [layout, setLayoutState] = useState<LayoutMode>(() => {
    const saved = localStorage.getItem("chart-layout");
    return (saved as LayoutMode) || "1";
  });

  useEffect(() => {
    localStorage.setItem("chart-layout", layout);
  }, [layout]);

  const setLayout = (mode: LayoutMode) => {
    setLayoutState(mode);
  };

  // Fetch active agent signals
  const { data: swingSignals } = useQuery({
    queryKey: ["agent-signals"],
    queryFn: fetchAgentSignals,
    refetchInterval: 10_000,
  });

  const { data: daySignals } = useQuery({
    queryKey: ["day-trade-signals"],
    queryFn: fetchDayTradeSignals,
    refetchInterval: 10_000,
  });

  const chartCount = getChartCount(layout);
  const gridClass = getGridClass(layout);

  // Merge all active signals for display
  const allSignals: Record<string, { type: string; entry: number; sl: number; tps: number[]; action: string; strategy: string; confidence: number }> = {};

  if (swingSignals) {
    for (const [sym, sig] of Object.entries(swingSignals)) {
      const normalSym = sym.replace("/", "");
      allSignals[normalSym] = {
        type: "swing", entry: sig.entry, sl: sig.stop_loss,
        tps: sig.tp_levels, action: sig.action,
        strategy: sig.strategy_name, confidence: sig.confidence,
      };
    }
  }
  if (daySignals) {
    for (const [sym, sig] of Object.entries(daySignals)) {
      const normalSym = sym.replace("/", "");
      allSignals[normalSym] = {
        type: "day", entry: sig.entry, sl: sig.stop_loss,
        tps: sig.tp_levels, action: sig.action,
        strategy: sig.strategy_type, confidence: sig.confidence,
      };
    }
  }

  return (
    <div className="space-y-2">
      {/* Layout controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-500 mr-2">Layout:</span>
          {LAYOUTS.map((l) => (
            <button key={l.mode} type="button" onClick={() => setLayout(l.mode)}
              className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                layout === l.mode ? "bg-accent text-white" : "bg-surface text-gray-400 hover:text-white border border-border"
              }`}
              aria-label={`Select ${l.label} layout`} title={l.label}>
              {l.label}
            </button>
          ))}
        </div>

        {/* Active positions indicator */}
        {Object.keys(allSignals).length > 0 && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-gray-500">Active Positions:</span>
            {Object.entries(allSignals).map(([sym, sig]) => (
              <span key={sym} className={`rounded px-2 py-0.5 font-mono ${
                sig.action === "LONG" ? "bg-bullish/20 text-bullish" : "bg-bearish/20 text-bearish"
              }`}>
                {sym} {sig.action}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Charts grid */}
      <div className={`grid ${gridClass} gap-2`}>
        {Array.from({ length: chartCount }).map((_, i) => (
          <div key={i} className={layout === "3" && i === 2 ? "col-span-2" : ""}>
            <PriceChart
              onAssetChange={i === 0 ? onAssetChange : undefined}
              activePosition={allSignals}
              compact={chartCount > 1}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
