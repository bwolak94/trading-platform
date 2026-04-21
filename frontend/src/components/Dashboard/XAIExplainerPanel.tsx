import React, { useState, useCallback } from "react";

interface FeatureImportance {
  feature: string;
  value: number;
  contribution: number;
  direction: "POSITIVE" | "NEGATIVE" | "NEUTRAL";
  weight: number;
  description: string;
  importance_rank: number;
  importance_pct: number;
}

interface XAIReport {
  feature_importances: FeatureImportance[];
  top_3_drivers: string[];
  explanation: string;
  chart_data: Array<{
    feature: string;
    value: number;
    abs_value: number;
    color: string;
    label: string;
    importance_pct: number;
  }>;
  signal_summary: {
    symbol: string;
    direction: string;
    confidence: number;
    strategy: string;
  };
}

interface Props {
  signal?: Record<string, unknown>;
  signalId?: string;
}

function FeatureBar({ item, maxAbs }: { item: FeatureImportance; maxAbs: number }) {
  const pct = maxAbs > 0 ? (Math.abs(item.contribution) / maxAbs) * 100 : 0;
  const color =
    item.direction === "POSITIVE"
      ? "bg-emerald-500"
      : item.direction === "NEGATIVE"
      ? "bg-red-500"
      : "bg-gray-600";
  const textColor =
    item.direction === "POSITIVE"
      ? "text-emerald-400"
      : item.direction === "NEGATIVE"
      ? "text-red-400"
      : "text-gray-400";

  return (
    <div className="flex items-center gap-3 py-1.5">
      <div className="w-5 text-[10px] text-gray-500 text-right shrink-0">#{item.importance_rank}</div>
      <div className="w-28 shrink-0">
        <p className="text-xs text-gray-300 truncate">{item.feature.replace(/_/g, " ")}</p>
        <p className="text-[10px] text-gray-500 truncate">{item.description}</p>
      </div>
      <div className="flex-1 relative">
        <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${color}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      <div className="w-16 text-right shrink-0">
        <span className={`text-xs font-mono ${textColor}`}>
          {item.contribution >= 0 ? "+" : ""}{item.contribution.toFixed(3)}
        </span>
      </div>
      <div className="w-8 text-right shrink-0">
        <span className="text-[10px] text-gray-500">{item.importance_pct.toFixed(0)}%</span>
      </div>
    </div>
  );
}

export const XAIExplainerPanel: React.FC<Props> = ({ signal, signalId }) => {
  const [report, setReport] = useState<XAIReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchExplanation = useCallback(async () => {
    if (!signal && !signalId) return;
    setLoading(true);
    setError(null);
    try {
      let data: XAIReport;
      if (signal) {
        const resp = await fetch("/api/v1/automation/xai-explain", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ signal }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        data = await resp.json();
      } else {
        const resp = await fetch(`/api/v1/signals/${signalId}/xai-explain`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        data = await resp.json();
      }
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate explanation");
    } finally {
      setLoading(false);
    }
  }, [signal, signalId]);

  const maxAbs = report
    ? Math.max(...report.feature_importances.map(f => Math.abs(f.contribution)))
    : 1;

  const summary = report?.signal_summary;
  const dirColor = summary?.direction === "LONG" ? "text-emerald-400" : "text-red-400";

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wider">XAI Signal Explainer</h3>
          <p className="text-[10px] text-gray-500 mt-0.5">Feature importance for signal generation</p>
        </div>
        <button
          onClick={fetchExplanation}
          disabled={loading || (!signal && !signalId)}
          aria-label="Generate XAI explanation"
          className="px-3 py-1 text-xs bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-white rounded-md transition-colors"
        >
          {loading ? "Analyzing…" : "Explain"}
        </button>
      </div>

      {error && (
        <div role="alert" className="text-xs text-red-400 bg-red-900/20 border border-red-700/30 rounded px-3 py-2">
          {error}
        </div>
      )}

      {!report && !loading && (
        <p className="text-xs text-gray-500 text-center py-6">
          Click Explain to generate an AI explanation for this signal.
        </p>
      )}

      {loading && (
        <div className="space-y-2 py-2">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-8 bg-gray-800 rounded animate-pulse" />
          ))}
        </div>
      )}

      {report && (
        <div className="flex flex-col gap-4">
          {/* Summary header */}
          {summary && (
            <div className="flex items-center gap-3 bg-gray-800 rounded-lg px-3 py-2">
              <span className={`text-sm font-bold ${dirColor}`}>{summary.direction}</span>
              <span className="text-sm text-gray-300">{summary.symbol}</span>
              <span className="text-xs text-gray-400">{summary.strategy?.replace(/_/g, " ")}</span>
              <span className="ml-auto text-xs text-gray-400">
                {((summary.confidence ?? 0) * 100).toFixed(0)}% confidence
              </span>
            </div>
          )}

          {/* Explanation text */}
          <div className="bg-purple-950/20 border border-purple-700/20 rounded-lg px-3 py-3">
            <p className="text-xs text-purple-200 leading-relaxed">{report.explanation}</p>
          </div>

          {/* Top 3 drivers */}
          <div className="flex gap-2">
            {report.top_3_drivers.map((driver, i) => (
              <span
                key={driver}
                className="text-[10px] px-2 py-1 bg-gray-800 text-gray-300 rounded-full"
              >
                #{i + 1} {driver.replace(/_/g, " ")}
              </span>
            ))}
          </div>

          {/* Feature bar chart */}
          <div>
            <div className="flex items-center gap-3 pb-2 mb-2 border-b border-gray-800">
              <div className="w-5" />
              <div className="w-28 text-[10px] text-gray-500">Feature</div>
              <div className="flex-1 text-[10px] text-gray-500">Importance</div>
              <div className="w-16 text-right text-[10px] text-gray-500">Contribution</div>
              <div className="w-8 text-right text-[10px] text-gray-500">%</div>
            </div>
            {report.feature_importances.map(item => (
              <FeatureBar key={item.feature} item={item} maxAbs={maxAbs} />
            ))}
          </div>

          {/* Legend */}
          <div className="flex gap-4 text-[10px] text-gray-500">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
              Positive (supports signal)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
              Negative (opposes signal)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-gray-600 inline-block" />
              Neutral
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default XAIExplainerPanel;
