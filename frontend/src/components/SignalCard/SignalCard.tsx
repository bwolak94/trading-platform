import { useState, useEffect, useCallback, useRef, memo } from "react";
import type { Signal } from "../../types";

// --------------- G1: Swipe gesture hook ---------------

type SwipeAction = "watch" | "dismiss" | null;

function useSwipeGesture(onSwipe: (action: SwipeAction) => void) {
  const touchStartX = useRef<number | null>(null);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0]?.clientX ?? null;
  }, []);

  const onTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (touchStartX.current === null) return;
      const deltaX = (e.changedTouches[0]?.clientX ?? 0) - touchStartX.current;
      touchStartX.current = null;
      if (Math.abs(deltaX) < 60) return; // dead zone
      onSwipe(deltaX > 0 ? "watch" : "dismiss");
    },
    [onSwipe],
  );

  return { onTouchStart, onTouchEnd };
}

// --------------- Signal age ---------------

function useSignalAgeMinutes(createdAt: string): number {
  const [ageMin, setAgeMin] = useState(() =>
    Math.floor((Date.now() - new Date(createdAt).getTime()) / 60000),
  );
  useEffect(() => {
    const timer = setInterval(() => {
      setAgeMin(Math.floor((Date.now() - new Date(createdAt).getTime()) / 60000));
    }, 60_000);
    return () => clearInterval(timer);
  }, [createdAt]);
  return ageMin;
}

function ageBadgeClass(ageMin: number): string {
  if (ageMin < 30) return "bg-bullish/15 text-bullish";
  if (ageMin < 120) return "bg-amber-500/20 text-amber-400";
  return "bg-bearish/20 text-bearish animate-pulse";
}

function fmtAge(ageMin: number): string {
  if (ageMin < 60) return `${ageMin}m`;
  return `${Math.floor(ageMin / 60)}h ${ageMin % 60}m`;
}

// --------------- Confidence trend ---------------

function useConfidenceTrend(signalId: string, currentConf: number): "up" | "down" | "flat" {
  const prevRef = useRef<number | null>(null);
  const key = `conf_prev_${signalId}`;

  const [trend, setTrend] = useState<"up" | "down" | "flat">(() => {
    try {
      const stored = localStorage.getItem(key);
      if (stored !== null) {
        const prev = parseFloat(stored);
        if (currentConf > prev + 1) return "up";
        if (currentConf < prev - 1) return "down";
      }
    } catch { /* ignore */ }
    return "flat";
  });

  useEffect(() => {
    try {
      const stored = localStorage.getItem(key);
      const prev = stored !== null ? parseFloat(stored) : null;
      if (prev !== null) {
        if (currentConf > prev + 1) setTrend("up");
        else if (currentConf < prev - 1) setTrend("down");
        else setTrend("flat");
      }
      localStorage.setItem(key, String(currentConf));
      prevRef.current = currentConf;
    } catch { /* ignore */ }
  }, [currentConf, key]);

  return trend;
}

const directionConfig = {
  LONG: { icon: "\u{1F7E2}", color: "text-bullish", border: "border-bullish/30" },
  SHORT: { icon: "\u{1F534}", color: "text-bearish", border: "border-bearish/30" },
  NEUTRAL: { icon: "\u26AA", color: "text-gray-400", border: "border-border" },
} as const;

// --------------- Sparkline hook ---------------

interface OHLCVBar {
  close: number;
}

interface SparklineState {
  prices: number[];
  isLoading: boolean;
  error: boolean;
}

// Module-level cache: symbol → { prices, expiresAt }
// In-flight map: symbol → Promise<number[]> — deduplicates concurrent requests for the same symbol
// (React Strict Mode fires effects twice; without in-flight dedup each card would launch 2 fetches)
const _sparklineCache = new Map<string, { prices: number[]; expiresAt: number }>();
const _sparklineInflight = new Map<string, Promise<number[]>>();
const _SPARKLINE_TTL_MS = 5 * 60 * 1000; // 5 minutes

function fetchSparklinePrices(symbol: string): Promise<number[]> {
  // Return in-flight promise if one already exists
  const inflight = _sparklineInflight.get(symbol);
  if (inflight) return inflight;

  const promise = fetch(`/api/v1/market/ohlcv?symbol=${symbol}&timeframe=1h&limit=24`)
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json() as Promise<OHLCVBar[] | { data: OHLCVBar[] }>;
    })
    .then((body) => {
      const bars: OHLCVBar[] = Array.isArray(body) ? body : (body as { data: OHLCVBar[] }).data ?? [];
      const prices = bars.map((b) => b.close).filter((p): p is number => typeof p === "number");
      _sparklineCache.set(symbol, { prices, expiresAt: Date.now() + _SPARKLINE_TTL_MS });
      return prices;
    })
    .finally(() => {
      _sparklineInflight.delete(symbol);
    });

  _sparklineInflight.set(symbol, promise);
  return promise;
}

function useSparkline(asset: string): SparklineState {
  const [state, setState] = useState<SparklineState>({
    prices: [],
    isLoading: true,
    error: false,
  });

  useEffect(() => {
    let cancelled = false;
    const symbol = asset.includes("USDT") ? asset : `${asset}USDT`;

    // Serve from cache if still fresh
    const cached = _sparklineCache.get(symbol);
    if (cached && Date.now() < cached.expiresAt) {
      setState({ prices: cached.prices, isLoading: false, error: false });
      return;
    }

    setState((s) => ({ ...s, isLoading: true }));

    fetchSparklinePrices(symbol)
      .then((prices) => {
        if (!cancelled) setState({ prices, isLoading: false, error: false });
      })
      .catch(() => {
        if (!cancelled) setState({ prices: [], isLoading: false, error: true });
      });

    return () => {
      cancelled = true;
    };
  }, [asset]);

  return state;
}

// --------------- Sparkline SVG ---------------

interface SparklineProps {
  prices: number[];
}

function Sparkline({ prices }: SparklineProps) {
  if (!prices || prices.length < 2) return null;

  const firstPrice = prices[0] ?? 0;
  const lastPrice = prices[prices.length - 1] ?? 0;

  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const width = 80;
  const height = 24;

  const points = prices
    .map((p, i) => {
      const x = (i / (prices.length - 1)) * width;
      const y = height - ((p - min) / range) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const isUp = lastPrice >= firstPrice;
  const color = isUp ? "#22c55e" : "#ef4444";

  return (
    <svg
      width={width}
      height={height}
      className="opacity-70"
      aria-label={`Price trend over 24h: ${isUp ? "up" : "down"}`}
      role="img"
    >
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function SparklineSkeleton() {
  return (
    <div
      className="h-6 w-20 animate-pulse rounded bg-border/40"
      aria-label="Loading sparkline"
      aria-busy="true"
    />
  );
}

// --------------- SparklineSection (fetches + renders) ---------------

function SparklineSection({ asset }: { asset: string }) {
  const { prices, isLoading } = useSparkline(asset);

  if (isLoading) return <SparklineSkeleton />;
  if (prices.length < 2) return null;

  const firstPrice = prices[0] ?? 0;
  const lastPrice = prices[prices.length - 1] ?? 0;
  const isUp = lastPrice >= firstPrice;
  const changePct =
    firstPrice !== 0
      ? (((lastPrice - firstPrice) / firstPrice) * 100).toFixed(2)
      : "0.00";

  return (
    <div className="flex items-center gap-2">
      <Sparkline prices={prices} />
      <span
        className={`font-mono text-xs ${isUp ? "text-green-400" : "text-red-400"}`}
        aria-label={`24h change: ${isUp ? "+" : ""}${changePct}%`}
      >
        {isUp ? "+" : ""}
        {changePct}%
      </span>
    </div>
  );
}

// --------------- SignalCard ---------------

interface SignalCardProps {
  signal: Signal;
  isNew?: boolean;
  /** Slip in basis points applied to entry (default 5bps) for adjusted R/R display */
  slippageBps?: number;
  /** If true, renders a "duplicate" badge — same asset+direction within 15 min */
  isDuplicate?: boolean;
  onNavigate?: (asset: string, timeframe?: string) => void;
}

export const SignalCard = memo(function SignalCard({ signal, isNew, slippageBps = 5, isDuplicate = false, onNavigate }: SignalCardProps) {
  const config = directionConfig[signal.direction] ?? directionConfig.NEUTRAL;
  const ageMin = useSignalAgeMinutes(signal.created_at);
  const confTrend = useConfidenceTrend(signal.id, signal.confidence ?? 0);

  // Slippage-adjusted R/R
  const slippageFactor = 1 + (slippageBps / 10000);
  const adjEntry = signal.direction === "LONG"
    ? (signal.entry_price ?? 0) * slippageFactor
    : (signal.entry_price ?? 0) / slippageFactor;
  const adjRR = signal.stop_loss && signal.take_profit_1 && adjEntry
    ? Math.abs(signal.take_profit_1 - adjEntry) / Math.abs(adjEntry - signal.stop_loss)
    : signal.risk_reward ?? 0;

  // G1: Swipe gestures — swipe right to Watch, left to Dismiss
  const [swipeHint, setSwipeHint] = useState<"watch" | "dismiss" | null>(null);
  const [watched, setWatched] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const handleSwipe = useCallback((action: SwipeAction) => {
    if (!action) return;
    setSwipeHint(action);
    if (action === "watch") setWatched(true);
    if (action === "dismiss") setDismissed(true);
    setTimeout(() => setSwipeHint(null), 800);
  }, []);

  const { onTouchStart, onTouchEnd } = useSwipeGesture(handleSwipe);

  const handleClick = () => {
    onNavigate?.(signal.asset);
  };

  if (dismissed) return null;

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
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
      className={`relative rounded-lg border ${config.border} bg-surface p-5 transition-all ${
        isNew ? "animate-pulse ring-1 ring-bullish/40" : ""
      } ${onNavigate ? "cursor-pointer hover:border-accent/50 hover:ring-1 hover:ring-accent/30" : ""}
      ${swipeHint === "watch" ? "ring-2 ring-bullish/60" : ""}
      ${swipeHint === "dismiss" ? "opacity-60 ring-2 ring-bearish/60" : ""}`}
      aria-label={onNavigate ? `Navigate chart to ${signal.asset}` : undefined}
    >
      {/* G1: Swipe action overlay */}
      {swipeHint && (
        <div className={`absolute inset-0 flex items-center justify-center rounded-lg text-xs font-bold pointer-events-none
          ${swipeHint === "watch" ? "bg-bullish/10 text-bullish" : "bg-bearish/10 text-bearish"}`}
          aria-hidden="true"
        >
          {swipeHint === "watch" ? "WATCHING" : "DISMISSED"}
        </div>
      )}
      {watched && (
        <div className="absolute right-2 top-2 rounded bg-bullish/20 px-1.5 py-0.5 text-[10px] font-semibold text-bullish pointer-events-none" aria-label="Signal marked as watched">
          WATCHING
        </div>
      )}
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className={`text-lg font-semibold ${config.color}`}>
            {config.icon} {signal.asset} {signal.direction}
          </h3>
          {isDuplicate && (
            <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-bold text-amber-400" title="Re-emit of a recent signal">
              DUP
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <span className={`rounded px-1.5 py-0.5 text-[9px] font-medium ${ageBadgeClass(ageMin)}`}>
            {fmtAge(ageMin)}
          </span>
          <span className="rounded bg-surface px-2 py-0.5 text-xs text-gray-400">
            {signal.status}
          </span>
        </div>
      </div>

      {/* Confidence */}
      <div className="mb-4">
        <div className="group relative">
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="text-gray-400">Confidence</span>
            <span className={`flex items-center gap-1 font-mono font-bold ${config.color}`}>
              {(signal.confidence ?? 0).toFixed(0)}%
              {confTrend === "up" && <span className="text-bullish text-xs" aria-label="Confidence rising">↑</span>}
              {confTrend === "down" && <span className="text-bearish text-xs" aria-label="Confidence falling">↓</span>}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-background">
            <div
              className={`h-full rounded-full ${
                signal.direction === "LONG" ? "bg-bullish" : "bg-bearish"
              }`}
              style={{ width: `${Math.min(signal.confidence ?? 0, 100)}%` }}
            />
          </div>
          {/* Confidence tooltip on hover */}
          <div className="absolute left-0 top-full z-30 mt-1 hidden w-64 rounded border border-border bg-surface p-2 shadow-lg group-hover:block">
            <p className="mb-1 text-xs text-gray-500">Score Breakdown:</p>
            {signal.factors.map((f, i) => (
              <div key={i} className="flex justify-between text-xs">
                <span className="text-gray-300">{f.name}</span>
                <span className="font-mono text-white">
                  {((f.weight ?? 0) * (f.score ?? 0) * 100).toFixed(0)}pts ({((f.weight ?? 0) * 100).toFixed(0)}%)
                </span>
              </div>
            ))}
          </div>
        </div>
        <p className="mt-1 text-sm text-gray-300">
          Probability of {signal.direction === "LONG" ? "upward" : "downward"}{" "}
          breakout: {(signal.confidence ?? 0).toFixed(0)}%
        </p>
      </div>

      {/* Sparkline — 24h price action */}
      <div className="mb-4 flex items-center justify-between">
        <span className="text-xs text-gray-500">24h Price</span>
        <SparklineSection asset={signal.asset} />
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
        <LevelRow label="Entry" value={signal.entry_price ?? 0} />
        <LevelRow label="SL" value={signal.stop_loss ?? 0} className="text-bearish" />
        <LevelRow label="TP1" value={signal.take_profit_1 ?? 0} className="text-bullish" />
        {signal.take_profit_2 != null && (
          <LevelRow label="TP2" value={signal.take_profit_2} className="text-bullish" />
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-border pt-3 text-xs text-gray-500">
        <span
          className="rounded bg-background px-2 py-0.5"
          title={`Slippage-adjusted R/R (${slippageBps}bps)`}
        >
          R/R {adjRR.toFixed(1)}
          {Math.abs(adjRR - (signal.risk_reward ?? 0)) > 0.05 && (
            <span className="ml-1 text-[9px] text-gray-600">
              ({(signal.risk_reward ?? 0).toFixed(1)} raw)
            </span>
          )}
        </span>
        <RegimeBadge regime={signal.regime} />
        <div className="flex items-center gap-2">
          <CopyButton signal={signal} />
          <div className="flex flex-col items-end gap-0.5">
            <span>{new Date(signal.created_at).toLocaleTimeString()}</span>
            {signal.expires_at && (
              <ExpiryCountdown expiresAt={signal.expires_at} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
// Memoized — only re-renders when signal.id or signal.updated_at changes
}, (prev, next) =>
  prev.signal.id === next.signal.id &&
  prev.signal.updated_at === next.signal.updated_at &&
  prev.isNew === next.isNew,
);

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

function CopyButton({ signal }: { signal: Signal }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const text = [
        `${signal.asset} ${signal.direction}`,
        `Entry: $${(signal.entry_price ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
        `SL: $${(signal.stop_loss ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
        `TP1: $${(signal.take_profit_1 ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
        signal.take_profit_2 != null ? `TP2: $${signal.take_profit_2.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : null,
        `R/R: ${(signal.risk_reward ?? 0).toFixed(1)} | Conf: ${(signal.confidence ?? 0).toFixed(0)}%`,
      ].filter(Boolean).join("\n");
      void navigator.clipboard.writeText(text).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      });
    },
    [signal],
  );

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="rounded p-1 text-gray-600 hover:text-gray-300 transition-colors"
      aria-label="Copy trade parameters to clipboard"
      title="Copy Entry / SL / TP"
    >
      {copied ? (
        <svg className="h-3.5 w-3.5 text-bullish" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
      )}
    </button>
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
