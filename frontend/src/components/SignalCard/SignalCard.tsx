import { useState, useEffect } from "react";
import type { Signal } from "../../types";

const directionConfig = {
  LONG: { icon: "\u{1F7E2}", color: "text-bullish", border: "border-bullish/30" },
  SHORT: { icon: "\u{1F534}", color: "text-bearish", border: "border-bearish/30" },
  NEUTRAL: { icon: "\u26AA", color: "text-gray-400", border: "border-border" },
} as const;

interface SignalCardProps {
  signal: Signal;
  isNew?: boolean;
  onNavigate?: (asset: string, timeframe?: string) => void;
}

export function SignalCard({ signal, isNew, onNavigate }: SignalCardProps) {
  const config = directionConfig[signal.direction] ?? directionConfig.NEUTRAL;

  const handleClick = () => {
    onNavigate?.(signal.asset);
  };

  return (
    <div
      role={onNavigate ? "button" : undefined}
      tabIndex={onNavigate ? 0 : undefined}
      onClick={handleClick}
      onKeyDown={(e) => {
        if (onNavigate && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          handleClick();
        }
      }}
      className={`rounded-lg border ${config.border} bg-surface p-5 transition-all ${
        isNew ? "animate-pulse ring-1 ring-bullish/40" : ""
      } ${onNavigate ? "cursor-pointer hover:border-accent/50 hover:ring-1 hover:ring-accent/30" : ""}`}
      aria-label={onNavigate ? `Navigate chart to ${signal.asset}` : undefined}
    >
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <h3 className={`text-lg font-semibold ${config.color}`}>
          {config.icon} {signal.asset} {signal.direction}
        </h3>
        <span className="rounded bg-surface px-2 py-0.5 text-xs text-gray-400">
          {signal.status}
        </span>
      </div>

      {/* Confidence */}
      <div className="mb-4">
        <div className="group relative">
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="text-gray-400">Confidence</span>
            <span className={`font-mono font-bold ${config.color}`}>
              {signal.confidence.toFixed(0)}%
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-background">
            <div
              className={`h-full rounded-full ${
                signal.direction === "LONG" ? "bg-bullish" : "bg-bearish"
              }`}
              style={{ width: `${Math.min(signal.confidence, 100)}%` }}
            />
          </div>
          {/* Confidence tooltip on hover */}
          <div className="absolute left-0 top-full z-30 mt-1 hidden w-64 rounded border border-border bg-surface p-2 shadow-lg group-hover:block">
            <p className="mb-1 text-xs text-gray-500">Score Breakdown:</p>
            {signal.factors.map((f, i) => (
              <div key={i} className="flex justify-between text-xs">
                <span className="text-gray-300">{f.name}</span>
                <span className="font-mono text-white">
                  {(f.weight * f.score * 100).toFixed(0)}pts ({(f.weight * 100).toFixed(0)}%)
                </span>
              </div>
            ))}
          </div>
        </div>
        <p className="mt-1 text-sm text-gray-300">
          Probability of {signal.direction === "LONG" ? "upward" : "downward"}{" "}
          breakout: {signal.confidence.toFixed(0)}%
        </p>
      </div>

      {/* Factors */}
      <div className="mb-4">
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
          Factors
        </h4>
        <div className="space-y-1">
          {signal.factors.slice(0, 3).map((factor, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <span className="text-gray-300">{factor.name}</span>
              <span className="font-mono text-gray-400">
                {(factor.weight * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Levels */}
      <div className="mb-3 grid grid-cols-2 gap-2">
        <LevelRow label="Entry" value={signal.entry_price} />
        <LevelRow label="SL" value={signal.stop_loss} className="text-bearish" />
        <LevelRow label="TP1" value={signal.take_profit_1} className="text-bullish" />
        <LevelRow label="TP2" value={signal.take_profit_2} className="text-bullish" />
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-border pt-3 text-xs text-gray-500">
        <span className="rounded bg-background px-2 py-0.5">
          R/R {signal.risk_reward.toFixed(1)}
        </span>
        <RegimeBadge regime={signal.regime} />
        <div className="flex flex-col items-end gap-0.5">
          <span>{new Date(signal.created_at).toLocaleTimeString()}</span>
          {signal.expires_at && (
            <ExpiryCountdown expiresAt={signal.expires_at} />
          )}
        </div>
      </div>
    </div>
  );
}

function LevelRow({
  label,
  value,
  className = "text-white",
}: {
  label: string;
  value: number;
  className?: string;
}) {
  return (
    <div className="flex items-center justify-between rounded bg-background px-2 py-1">
      <span className="text-xs text-gray-500">{label}</span>
      <span className={`font-mono text-sm ${className}`}>
        ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
    </div>
  );
}

const regimeColors: Record<string, string> = {
  TREND_BULL: "bg-bullish/20 text-bullish",
  TREND_BEAR: "bg-bearish/20 text-bearish",
  CONSOLIDATION: "bg-yellow-500/20 text-yellow-400",
  HIGH_VOL_CHOPPY: "bg-warning/20 text-warning",
};

function RegimeBadge({ regime }: { regime: string }) {
  const cls = regimeColors[regime] ?? "bg-gray-700 text-gray-400";
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${cls}`}>
      {regime.replace("_", " ")}
    </span>
  );
}

function ExpiryCountdown({ expiresAt }: { expiresAt: string }) {
  const [remaining, setRemaining] = useState("");
  const [urgency, setUrgency] = useState<"normal" | "warning" | "critical" | "expired">("normal");

  useEffect(() => {
    const compute = () => {
      const diff = new Date(expiresAt).getTime() - Date.now();
      if (diff <= 0) {
        setRemaining("Expired");
        setUrgency("expired");
        return;
      }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      setRemaining(`${h}h ${m}m`);
      if (h < 1) setUrgency("critical");
      else if (h < 4) setUrgency("warning");
      else setUrgency("normal");
    };
    compute();
    const timer = setInterval(compute, 30000);
    return () => clearInterval(timer);
  }, [expiresAt]);

  const colorClass = {
    normal: "text-gray-500",
    warning: "text-yellow-400",
    critical: "text-bearish animate-pulse",
    expired: "text-bearish",
  }[urgency];

  return (
    <span className={`text-xs ${colorClass}`} aria-label={`Expires in ${remaining}`}>
      Expires: {remaining}
    </span>
  );
}
