import React, { useState, useCallback } from "react";

interface TakeProfit {
  level: string;
  price: number;
  pct_gain: number;
  r_multiple: number;
  size_pct: number;
}

interface Playbook {
  symbol: string;
  direction: string;
  strategy: string;
  confidence: number;
  entry: { price: number; type: string; zone: [number, number] };
  stop_loss: { price: number; pct_from_entry: number; r_distance: number };
  take_profits: TakeProfit[];
  invalidation: { price: number; condition: string };
  checklist: string[];
  risk_reward_ratio: number;
  max_hold_time: string;
  notes: string;
}

interface Props {
  signalId?: string;
  signal?: Record<string, unknown>;
  currentPrice?: number;
}

export const PlaybookPanel: React.FC<Props> = ({ signalId, signal, currentPrice = 0 }) => {
  const [playbook, setPlaybook] = useState<Playbook | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checkedItems, setCheckedItems] = useState<Set<number>>(new Set());

  const fetchPlaybook = useCallback(async () => {
    if (!signal && !signalId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch("/api/v1/automation/playbook", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          signal: signal ?? { id: signalId },
          current_price: currentPrice,
          atr_value: 0,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: Playbook = await resp.json();
      setPlaybook(data);
      setCheckedItems(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate playbook");
    } finally {
      setLoading(false);
    }
  }, [signal, signalId, currentPrice]);

  const toggleCheck = (idx: number) => {
    setCheckedItems(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const dirColor = playbook?.direction === "LONG" ? "text-emerald-400" : "text-red-400";
  const dirBg = playbook?.direction === "LONG" ? "bg-emerald-500/10 border-emerald-500/30" : "bg-red-500/10 border-red-500/30";

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wider">Trade Playbook</h3>
        <button
          onClick={fetchPlaybook}
          disabled={loading || (!signal && !signalId)}
          aria-label="Generate playbook"
          className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white rounded-md transition-colors"
        >
          {loading ? "Generating…" : "Generate"}
        </button>
      </div>

      {error && (
        <div role="alert" className="text-xs text-red-400 bg-red-900/20 border border-red-700/30 rounded px-3 py-2">
          {error}
        </div>
      )}

      {!playbook && !loading && (
        <p className="text-xs text-gray-500 text-center py-6">
          Click Generate to create a trade playbook for the selected signal.
        </p>
      )}

      {playbook && (
        <div className="flex flex-col gap-3">
          {/* Header */}
          <div className={`flex items-center gap-3 p-3 rounded-lg border ${dirBg}`}>
            <span className={`text-lg font-bold ${dirColor}`}>{playbook.direction}</span>
            <span className="text-sm text-gray-300 font-medium">{playbook.symbol}</span>
            <span className="text-xs text-gray-400">{playbook.strategy.replace(/_/g, " ")}</span>
            <span className="ml-auto text-xs text-gray-400">
              Confidence: <span className="text-white font-medium">{(playbook.confidence * 100).toFixed(0)}%</span>
            </span>
          </div>

          {/* Levels grid */}
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-gray-800 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Entry ({playbook.entry.type})</p>
              <p className="text-sm font-mono font-semibold text-white">{playbook.entry.price.toFixed(4)}</p>
              <p className="text-xs text-gray-500">
                Zone: {playbook.entry.zone[0].toFixed(4)} – {playbook.entry.zone[1].toFixed(4)}
              </p>
            </div>
            <div className="bg-red-950/30 border border-red-800/30 rounded-lg p-3">
              <p className="text-xs text-red-400 mb-1">Stop Loss</p>
              <p className="text-sm font-mono font-semibold text-red-300">{playbook.stop_loss.price.toFixed(4)}</p>
              <p className="text-xs text-gray-500">−{playbook.stop_loss.pct_from_entry.toFixed(2)}%</p>
            </div>
          </div>

          {/* Take profits */}
          <div className="flex flex-col gap-1">
            <p className="text-xs text-gray-500 mb-1">Take Profits</p>
            {playbook.take_profits.map(tp => (
              <div key={tp.level} className="flex items-center gap-2 bg-emerald-950/20 border border-emerald-800/20 rounded px-3 py-2">
                <span className="text-xs font-medium text-emerald-400 w-8">{tp.level}</span>
                <span className="text-xs font-mono text-white">{tp.price.toFixed(4)}</span>
                <span className="text-xs text-emerald-400">+{tp.pct_gain.toFixed(2)}%</span>
                <span className="text-xs text-gray-400">{tp.r_multiple}R</span>
                <span className="ml-auto text-xs text-gray-500">{tp.size_pct}% size</span>
              </div>
            ))}
          </div>

          {/* R:R and hold time */}
          <div className="flex gap-2 text-xs">
            <div className="flex-1 bg-gray-800 rounded px-3 py-2">
              <span className="text-gray-500">R:R </span>
              <span className="text-white font-semibold">{playbook.risk_reward_ratio.toFixed(2)}:1</span>
            </div>
            <div className="flex-1 bg-gray-800 rounded px-3 py-2">
              <span className="text-gray-500">Hold: </span>
              <span className="text-gray-300">{playbook.max_hold_time}</span>
            </div>
          </div>

          {/* Invalidation */}
          <div className="bg-yellow-950/20 border border-yellow-700/20 rounded px-3 py-2">
            <p className="text-xs text-yellow-400">⚠️ Invalidation</p>
            <p className="text-xs text-gray-300">{playbook.invalidation.condition}</p>
          </div>

          {/* Checklist */}
          <div className="flex flex-col gap-1">
            <p className="text-xs text-gray-500 mb-1">Pre-Trade Checklist ({checkedItems.size}/{playbook.checklist.length})</p>
            {playbook.checklist.map((item, idx) => (
              <label key={idx} className="flex items-start gap-2 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={checkedItems.has(idx)}
                  onChange={() => toggleCheck(idx)}
                  className="mt-0.5 accent-blue-500"
                  aria-label={item}
                />
                <span className={`text-xs transition-colors ${checkedItems.has(idx) ? "line-through text-gray-500" : "text-gray-300 group-hover:text-white"}`}>
                  {item}
                </span>
              </label>
            ))}
          </div>

          {/* Notes */}
          {playbook.notes && (
            <p className="text-xs text-gray-400 italic border-t border-gray-700 pt-2">{playbook.notes}</p>
          )}
        </div>
      )}
    </div>
  );
};

export default PlaybookPanel;
