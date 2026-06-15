import React, { useState, useCallback } from "react";

// --------------- Interfaces ---------------

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
  chart_data: {
    feature: string;
    value: number;
    abs_value: number;
    color: string;
    label: string;
    importance_pct: number;
  }[];
  signal_summary: {
    symbol: string;
    direction: string;
    confidence: number;
    strategy: string;
    technical_score?: number;
    sentiment_score?: number;
    onchain_score?: number;
  };
}

interface Props {
  signal?: Record<string, unknown>;
  signalId?: string;
}

// --------------- Helpers ---------------

/**
 * Parse explanation text into numbered steps.
 * Handles formats like "1. Step text", "Step 1: text", or falls back to sentences.
 */
function parseExplanationSteps(explanation: string): string[] {
  // Try "1. …" or "1) …" format
  const numberedPattern = /^\d+[.)]\s+/;
  const byNumber = explanation
    .split(/\n/)
    .map((l) => l.trim())
    .filter((l) => numberedPattern.test(l));

  if (byNumber.length >= 2) {
    return byNumber.map((l) => l.replace(/^\d+[.)]\s+/, "").trim());
  }

  // Try splitting on sentence boundaries (max 6 steps)
  const sentences = explanation.match(/[^.!?]+[.!?]+/g) ?? [explanation];
  return sentences.map((s) => s.trim()).filter(Boolean).slice(0, 6);
}

const RISK_KEYWORDS = [
  "risk", "danger", "warning", "caution", "bearish", "decline", "loss",
  "volatile", "uncertainty", "concern", "drawdown", "stop",
];

function containsRiskLanguage(text: string): boolean {
  const lower = text.toLowerCase();
  return RISK_KEYWORDS.some((kw) => lower.includes(kw));
}

async function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard) {
    await navigator.clipboard.writeText(text);
  } else {
    // Fallback for environments without Clipboard API
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
}

// --------------- Sub-components ---------------

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
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
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

interface ScoreBarProps {
  label: string;
  value: number | undefined;
  color?: string;
}

function ScoreBar({ label, value, color = "bg-blue-500" }: ScoreBarProps) {
  if (value === undefined || value === null) return null;
  const pct = Math.min(Math.abs(value) * 100, 100);

  return (
    <div>
      <div className="mb-0.5 flex items-center justify-between text-[10px] text-gray-500">
        <span>{label}</span>
        <span className="font-mono">{(value * 100).toFixed(0)}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${label}: ${pct.toFixed(0)}%`}
        />
      </div>
    </div>
  );
}

interface ChainOfThoughtProps {
  explanation: string;
}

function ChainOfThought({ explanation }: ChainOfThoughtProps) {
  const steps = parseExplanationSteps(explanation);
  const hasRisk = containsRiskLanguage(explanation);
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    await copyToClipboard(explanation);
    setCopied(true);
    setTimeout(() => { setCopied(false); }, 2000);
  }, [explanation]);

  return (
    <div className="flex flex-col gap-3">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <h4 className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
          Reasoning Chain
        </h4>
        <div className="flex items-center gap-2">
          {hasRisk && (
            <span
              className="flex items-center gap-1 rounded bg-red-900/40 px-2 py-0.5 text-[10px] font-medium text-red-400 border border-red-700/30"
              role="status"
              aria-label="Explanation contains risk factors"
            >
              <span aria-hidden="true">⚠</span> Key Risk
            </span>
          )}
          <button
            type="button"
            onClick={handleCopy}
            aria-label="Copy full explanation to clipboard"
            className="flex items-center gap-1 rounded border border-border px-2 py-0.5 text-[10px] text-gray-400 hover:border-gray-500 hover:text-gray-200 transition-colors"
          >
            {copied ? (
              <>
                <span aria-hidden="true">✓</span> Copied
              </>
            ) : (
              <>
                <span aria-hidden="true">⎘</span> Copy
              </>
            )}
          </button>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {steps.map((step, i) => (
          <div key={i} className="flex gap-2">
            <div
              className="flex-shrink-0 w-5 h-5 rounded-full bg-accent/20 text-accent text-xs flex items-center justify-center font-bold"
              aria-hidden="true"
            >
              {i + 1}
            </div>
            <p className="text-xs text-gray-300 leading-relaxed pt-0.5">{step}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// --------------- Main panel ---------------

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
    ? Math.max(...report.feature_importances.map((f) => Math.abs(f.contribution)))
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
        <div className="space-y-2 py-2" aria-busy="true" aria-label="Generating explanation">
          {Array.from({ length: 6 }).map((_, i) => (
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

          {/* Chain-of-thought explanation */}
          <div className="bg-purple-950/20 border border-purple-700/20 rounded-lg px-3 py-3">
            <ChainOfThought explanation={report.explanation} />
          </div>

          {/* Confidence Breakdown */}
          {summary && (
            <div className="rounded-lg bg-gray-800/60 px-3 py-3">
              <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                Confidence Breakdown
              </h4>
              <div className="space-y-2">
                <ScoreBar label="Technical Score" value={summary.technical_score} color="bg-blue-500" />
                <ScoreBar label="Sentiment Score" value={summary.sentiment_score} color="bg-purple-500" />
                <ScoreBar label="On-Chain Score" value={summary.onchain_score} color="bg-cyan-500" />
              </div>
            </div>
          )}

          {/* Top 3 drivers */}
          <div className="flex gap-2 flex-wrap">
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
            {report.feature_importances.map((item) => (
              <FeatureBar key={item.feature} item={item} maxAbs={maxAbs} />
            ))}
          </div>

          {/* Legend */}
          <div className="flex gap-4 text-[10px] text-gray-500">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" aria-hidden="true" />
              Positive (supports signal)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-500 inline-block" aria-hidden="true" />
              Negative (opposes signal)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-gray-600 inline-block" aria-hidden="true" />
              Neutral
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default XAIExplainerPanel;
