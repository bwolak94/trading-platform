import { useState } from "react";
import { runAnalysis, type AnalysisResult } from "../../api/client";

const ASSETS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];
const TIMEFRAMES = ["1h", "4h", "1d"];
const STRATEGIES = [
  { value: "", label: "All Strategies" },
  { value: "trend_following", label: "Trend Following" },
  { value: "mean_reversion", label: "Mean Reversion" },
  { value: "smc", label: "SMC (Smart Money)" },
  { value: "volume_breakout", label: "Volume Breakout" },
];

const regimeColors: Record<string, string> = {
  TREND_BULL: "text-bullish",
  TREND_BEAR: "text-bearish",
  CONSOLIDATION: "text-yellow-400",
  HIGH_VOL_CHOPPY: "text-warning",
};

export function AnalysisPanel() {
  const [asset, setAsset] = useState("BTC/USDT");
  const [tf, setTf] = useState("4h");
  const [strategy, setStrategy] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await runAnalysis(asset, tf, strategy || undefined);
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-gray-500">
        AI Strategy Analysis
      </h2>

      {/* Controls */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs text-gray-500">Asset</label>
          <select value={asset} onChange={(e) => setAsset(e.target.value)}
            className="rounded border border-border bg-background px-3 py-1.5 text-sm text-white" aria-label="Asset">
            {ASSETS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500">Timeframe</label>
          <select value={tf} onChange={(e) => setTf(e.target.value)}
            className="rounded border border-border bg-background px-3 py-1.5 text-sm text-white" aria-label="Timeframe">
            {TIMEFRAMES.map((t) => <option key={t} value={t}>{t.toUpperCase()}</option>)}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500">Strategy</label>
          <select value={strategy} onChange={(e) => setStrategy(e.target.value)}
            className="rounded border border-border bg-background px-3 py-1.5 text-sm text-white" aria-label="Strategy">
            {STRATEGIES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
        <button type="button" onClick={() => void handleRun()} disabled={loading}
          className="rounded bg-accent px-4 py-1.5 text-sm font-medium text-white hover:bg-accent/80 disabled:opacity-50"
          aria-label="Run analysis">
          {loading ? "Analyzing..." : "Run Analysis"}
        </button>
      </div>

      {error && <p className="mb-3 text-sm text-bearish">{error}</p>}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Market Summary */}
          <div className="rounded bg-background p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold text-white">{result.asset} — Market Summary</span>
              <span className={`rounded px-2 py-0.5 text-xs font-bold ${regimeColors[result.regime.regime] ?? "text-gray-400"}`}>
                {result.regime.regime.replace("_", " ")} ({result.regime.confidence.toFixed(0)}%)
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs lg:grid-cols-5">
              <Stat label="Price" value={`$${result.summary.price.toLocaleString()}`} />
              <Stat label="RSI(14)" value={result.summary.rsi.toFixed(1)}
                color={result.summary.rsi > 70 ? "text-bearish" : result.summary.rsi < 30 ? "text-bullish" : "text-white"} />
              <Stat label="ADX(14)" value={result.summary.adx.toFixed(1)}
                color={result.summary.adx > 25 ? "text-bullish" : "text-gray-400"} />
              <Stat label="Vol vs Avg" value={`${result.summary.volume_vs_avg.toFixed(1)}x`}
                color={result.summary.volume_vs_avg > 1.5 ? "text-bullish" : "text-gray-400"} />
              <Stat label="BB Position" value={result.summary.bb_position.toFixed(2)}
                color={result.summary.bb_position > 0.8 ? "text-bearish" : result.summary.bb_position < 0.2 ? "text-bullish" : "text-white"} />
              <Stat label="ATR %" value={`${result.summary.atr_normalized.toFixed(2)}%`} />
              <Stat label="EMA Trend" value={result.summary.ema_cross === 1 ? "Bullish" : result.summary.ema_cross === -1 ? "Bearish" : "Neutral"}
                color={result.summary.ema_cross === 1 ? "text-bullish" : result.summary.ema_cross === -1 ? "text-bearish" : "text-gray-400"} />
            </div>
          </div>

          {/* Strategy Results */}
          <div className="space-y-2">
            <h3 className="text-xs font-medium uppercase tracking-wide text-gray-500">Strategy Results</h3>
            {result.strategies.map((s) => (
              <div key={s.name} className={`rounded border p-3 ${s.signal ? "border-bullish/30 bg-bullish/5" : "border-border bg-background"}`}>
                <div className="mb-1 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-white">{formatStrategyName(s.name)}</span>
                    {s.compatible_with_regime ? (
                      <span className="rounded bg-bullish/20 px-1.5 py-0.5 text-xs text-bullish">Compatible</span>
                    ) : (
                      <span className="rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-400">Incompatible</span>
                    )}
                  </div>
                  {s.signal && (
                    <span className={`rounded px-2 py-0.5 text-xs font-bold ${s.signal.direction === "LONG" ? "bg-bullish/20 text-bullish" : "bg-bearish/20 text-bearish"}`}>
                      {s.signal.direction} — {s.signal.confidence.toFixed(0)}%
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500">{s.description}</p>

                {s.signal ? (
                  <div className="mt-2 space-y-2">
                    {/* Levels */}
                    <div className="flex flex-wrap gap-3 text-xs">
                      <span className="text-gray-400">Entry: <span className="font-mono text-white">${s.signal.entry_price.toLocaleString()}</span></span>
                      <span className="text-gray-400">SL: <span className="font-mono text-bearish">${s.signal.stop_loss.toLocaleString()}</span></span>
                      <span className="text-gray-400">TP1: <span className="font-mono text-bullish">${s.signal.take_profit_1.toLocaleString()}</span></span>
                      <span className="text-gray-400">TP2: <span className="font-mono text-bullish">${s.signal.take_profit_2.toLocaleString()}</span></span>
                      <span className="text-gray-400">R/R: <span className="font-mono text-white">{s.signal.risk_reward.toFixed(1)}</span></span>
                    </div>
                    {/* Factors */}
                    <div className="flex flex-wrap gap-2">
                      {s.signal.factors.map((f, i) => (
                        <span key={i} className={`rounded px-2 py-0.5 text-xs ${f.label === "BULLISH" ? "bg-bullish/10 text-bullish" : "bg-bearish/10 text-bearish"}`}>
                          {f.name} ({(f.weight * 100).toFixed(0)}%)
                        </span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="mt-1 text-xs text-gray-500 italic">{s.reason}</p>
                )}
              </div>
            ))}
          </div>

          <p className="text-right text-xs text-gray-600">
            Analyzed at {new Date(result.timestamp).toLocaleTimeString()}
          </p>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color = "text-white" }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded bg-surface px-2 py-1">
      <span className="block text-gray-500">{label}</span>
      <span className={`font-mono font-semibold ${color}`}>{value}</span>
    </div>
  );
}

function formatStrategyName(name: string): string {
  return name.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}
