import type { SentimentData } from "../../types";

interface SentimentBarProps {
  sentiments: SentimentData[];
}

export function SentimentBar({ sentiments }: SentimentBarProps) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-gray-500">
        Sentiment
      </h2>
      <div className="space-y-2">
        {sentiments.length === 0 && (
          <p className="text-sm text-gray-500">No sentiment data available</p>
        )}
        {sentiments.map((s) => {
          const normalized = (s.score + 1) / 2; // map [-1,1] -> [0,1]
          const barColor =
            s.score > 0.2
              ? "bg-bullish"
              : s.score < -0.2
                ? "bg-bearish"
                : "bg-gray-500";
          const label =
            s.score > 0.2
              ? "Bullish"
              : s.score < -0.2
                ? "Bearish"
                : "Neutral";

          return (
            <div key={s.asset} className="rounded bg-background px-3 py-2">
              <div className="mb-1 flex items-center justify-between text-sm">
                <span className="font-mono text-white">{s.asset}</span>
                <span className="text-gray-400">
                  {label} ({s.score.toFixed(2)})
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-background">
                <div
                  className={`h-full rounded-full ${barColor}`}
                  style={{ width: `${normalized * 100}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
