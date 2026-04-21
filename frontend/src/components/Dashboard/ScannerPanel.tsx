import React, { useEffect, useState, useCallback } from "react";

interface Setup {
  symbol: string;
  long_score: number;
  short_score: number;
  bias: string;
  current_price: number;
  rsi: number;
  signals: string[];
  reason: string;
  strategy_hint: string;
}

interface ScanResult {
  timestamp: number;
  top_longs: Setup[];
  top_shorts: Setup[];
  total_scanned: number;
  scan_duration_ms: number;
}

const REFRESH_INTERVAL = 60_000; // 60 seconds

function ScoreBar({ score, max = 5, color }: { score: number; max?: number; color: string }) {
  const pct = Math.min(100, (score / max) * 100);
  return (
    <div className="w-16 h-1.5 bg-gray-700 rounded-full overflow-hidden">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function SetupRow({ setup, direction }: { setup: Setup; direction: "LONG" | "SHORT" }) {
  const score = direction === "LONG" ? setup.long_score : setup.short_score;
  const color = direction === "LONG" ? "bg-emerald-500" : "bg-red-500";
  const badgeColor = direction === "LONG" ? "text-emerald-400 bg-emerald-500/10" : "text-red-400 bg-red-500/10";

  return (
    <div className="flex items-center gap-3 py-2 border-b border-gray-800 last:border-0">
      <span className={`text-xs font-mono font-semibold px-2 py-0.5 rounded ${badgeColor}`}>
        {setup.symbol.replace("USDT", "")}
      </span>
      <div className="flex flex-col gap-0.5 flex-1 min-w-0">
        <p className="text-xs text-gray-300 truncate">{setup.reason}</p>
        <div className="flex gap-1 flex-wrap">
          {setup.signals.slice(0, 2).map((sig, i) => (
            <span key={i} className="text-[10px] text-gray-500 bg-gray-800 px-1.5 rounded">
              {sig}
            </span>
          ))}
        </div>
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
        <ScoreBar score={score} color={color} />
        <span className="text-[10px] text-gray-500">RSI {setup.rsi.toFixed(0)}</span>
      </div>
    </div>
  );
}

export const ScannerPanel: React.FC = () => {
  const [data, setData] = useState<ScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch("/api/v1/automation/scanner/top-setups?top_n=5");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const result: ScanResult = await resp.json();
      setData(result);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchData]);

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wider">Asset Scanner</h3>
          {lastUpdated && (
            <p className="text-[10px] text-gray-500 mt-0.5">
              Updated {lastUpdated.toLocaleTimeString()} · {data?.total_scanned ?? 0} scanned · {data?.scan_duration_ms ?? 0}ms
            </p>
          )}
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          aria-label="Refresh scanner"
          className="p-1.5 rounded-md text-gray-400 hover:text-white hover:bg-gray-800 transition-colors disabled:opacity-40"
        >
          <svg className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>

      {error && (
        <div role="alert" className="text-xs text-red-400 bg-red-900/20 border border-red-700/30 rounded px-3 py-2">
          {error}
        </div>
      )}

      {loading && !data && (
        <div className="space-y-2 py-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-10 bg-gray-800 rounded animate-pulse" />
          ))}
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Top Longs */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-semibold text-emerald-400">🟢 TOP LONGS</span>
              <span className="text-[10px] text-gray-500">({data.top_longs.length} setups)</span>
            </div>
            {data.top_longs.length === 0 ? (
              <p className="text-xs text-gray-500 text-center py-4">No long setups found</p>
            ) : (
              data.top_longs.map(setup => (
                <SetupRow key={setup.symbol} setup={setup} direction="LONG" />
              ))
            )}
          </div>

          {/* Top Shorts */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-semibold text-red-400">🔴 TOP SHORTS</span>
              <span className="text-[10px] text-gray-500">({data.top_shorts.length} setups)</span>
            </div>
            {data.top_shorts.length === 0 ? (
              <p className="text-xs text-gray-500 text-center py-4">No short setups found</p>
            ) : (
              data.top_shorts.map(setup => (
                <SetupRow key={setup.symbol} setup={setup} direction="SHORT" />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ScannerPanel;
