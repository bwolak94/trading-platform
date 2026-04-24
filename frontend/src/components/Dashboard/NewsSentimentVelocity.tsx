/**
 * Real-time News Sentiment Velocity Feed
 * Scrolling ticker of news headlines with sentiment scores
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchNews, fetchSentimentSnapshot } from "../../api/client";

type SentimentLabel = "POSITIVE" | "NEGATIVE" | "NEUTRAL";

function getSentimentLabel(score: number): SentimentLabel {
  if (score > 0.2) return "POSITIVE";
  if (score < -0.2) return "NEGATIVE";
  return "NEUTRAL";
}

const SENTIMENT_STYLES: Record<
  SentimentLabel,
  { badge: string; dot: string }
> = {
  POSITIVE: {
    badge: "bg-bullish/10 text-bullish border-bullish/30",
    dot: "bg-bullish",
  },
  NEGATIVE: {
    badge: "bg-bearish/10 text-bearish border-bearish/30",
    dot: "bg-bearish",
  },
  NEUTRAL: {
    badge: "bg-gray-500/10 text-gray-400 border-gray-500/30",
    dot: "bg-gray-500",
  },
};

const TRACKED_ASSETS = [
  "ALL", "BTC", "ETH", "SOL", "BNB", "XRP",
];

function SkeletonItem() {
  return (
    <div className="flex items-start gap-2 py-2 border-b border-border/20">
      <div className="mt-1 h-1.5 w-1.5 animate-pulse rounded-full bg-white/10" />
      <div className="flex-1 space-y-1">
        <div className="h-3 w-3/4 animate-pulse rounded bg-white/10" />
        <div className="h-2 w-1/3 animate-pulse rounded bg-white/10" />
      </div>
    </div>
  );
}

export function NewsSentimentVelocity() {
  const [selectedAsset, setSelectedAsset] = useState("ALL");
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(0);

  const { data: newsData, isLoading: newsLoading, isError } = useQuery({
    queryKey: ["news-sentiment-feed"],
    queryFn: () => fetchNews(30),
    refetchInterval: 60_000,
    retry: false,
  });

  const { data: sentimentData } = useQuery({
    queryKey: ["sentiment-snapshot"],
    queryFn: fetchSentimentSnapshot,
    refetchInterval: 60_000,
    retry: false,
  });

  const allNews = newsData?.news ?? [];

  const filtered = useMemo(() => {
    if (selectedAsset === "ALL") return allNews;
    return allNews.filter(
      (n) =>
        n.keywords?.some((k) =>
          k.toLowerCase().includes(selectedAsset.toLowerCase()),
        ) ||
        n.title.toLowerCase().includes(selectedAsset.toLowerCase()),
    );
  }, [allNews, selectedAsset]);

  // Auto-scroll to top when new items arrive
  useEffect(() => {
    if (filtered.length > prevCountRef.current && scrollRef.current) {
      scrollRef.current.scrollTo({ top: 0, behavior: "smooth" });
    }
    prevCountRef.current = filtered.length;
  }, [filtered.length]);

  const avgSentiment = useMemo(() => {
    if (filtered.length === 0) return 0;
    return filtered.reduce((sum, n) => sum + n.sentiment, 0) / filtered.length;
  }, [filtered]);

  const sentimentVelocity = useMemo(() => {
    if (filtered.length < 2) return 0;
    const recent = filtered.slice(0, Math.min(5, filtered.length));
    const older = filtered.slice(
      Math.min(5, filtered.length),
      Math.min(10, filtered.length),
    );
    if (older.length === 0) return 0;
    const recentAvg = recent.reduce((s, n) => s + n.sentiment, 0) / recent.length;
    const olderAvg = older.reduce((s, n) => s + n.sentiment, 0) / older.length;
    return recentAvg - olderAvg;
  }, [filtered]);

  const avgLabel = getSentimentLabel(avgSentiment);
  const velocityDir =
    sentimentVelocity > 0.05 ? "rising" : sentimentVelocity < -0.05 ? "falling" : "stable";

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">News Sentiment Feed</h2>
          <div className="mt-0.5 flex items-center gap-2 text-xs">
            <span className="text-gray-500">1h avg:</span>
            <span
              className={
                avgLabel === "POSITIVE"
                  ? "text-bullish"
                  : avgLabel === "NEGATIVE"
                    ? "text-bearish"
                    : "text-gray-400"
              }
            >
              {avgSentiment >= 0 ? "+" : ""}
              {(avgSentiment * 100).toFixed(0)}
            </span>
            <span
              className={`text-[10px] ${
                velocityDir === "rising"
                  ? "text-bullish"
                  : velocityDir === "falling"
                    ? "text-bearish"
                    : "text-gray-500"
              }`}
            >
              {velocityDir === "rising" ? "▲ rising" : velocityDir === "falling" ? "▼ falling" : "→ stable"}
            </span>
          </div>
        </div>
        <select
          value={selectedAsset}
          onChange={(e) => setSelectedAsset(e.target.value)}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent"
          aria-label="Filter news by asset"
        >
          {TRACKED_ASSETS.map((asset) => (
            <option key={asset} value={asset}>
              {asset === "ALL" ? "All Assets" : asset}
            </option>
          ))}
        </select>
      </div>

      {/* Aggregate sentiment from backend */}
      {sentimentData && (
        <div className="mb-3 flex gap-3 text-xs">
          <div className="rounded bg-white/5 px-2 py-1">
            <span className="text-gray-500">Global: </span>
            <span
              className={
                sentimentData.global_sentiment > 0 ? "text-bullish" : "text-bearish"
              }
            >
              {(sentimentData.global_sentiment * 100).toFixed(0)}
            </span>
          </div>
          <div className="rounded bg-white/5 px-2 py-1">
            <span className="text-gray-500">Crypto: </span>
            <span
              className={
                sentimentData.crypto_sentiment > 0 ? "text-bullish" : "text-bearish"
              }
            >
              {(sentimentData.crypto_sentiment * 100).toFixed(0)}
            </span>
          </div>
          {sentimentData.emergency_active && (
            <div className="rounded bg-bearish/10 px-2 py-1 text-bearish">
              ALERT: {sentimentData.emergency_reason}
            </div>
          )}
        </div>
      )}

      {isError && (
        <div className="mb-3 rounded bg-bearish/10 px-3 py-2 text-xs text-bearish">
          News feed unavailable
        </div>
      )}

      <div ref={scrollRef} className="max-h-72 overflow-y-auto space-y-0 pr-1">
        {newsLoading ? (
          <div>
            {[...Array(6)].map((_, i) => (
              <SkeletonItem key={i} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <p className="py-6 text-center text-xs text-gray-500">No recent news</p>
        ) : (
          filtered.map((item, idx) => {
            const label = getSentimentLabel(item.sentiment);
            const styles = SENTIMENT_STYLES[label];
            return (
              <div
                key={`${item.title}-${idx}`}
                className="flex items-start gap-2 border-b border-border/20 py-2 last:border-0"
              >
                <span
                  className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${styles.dot}`}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <p className="line-clamp-2 text-xs text-gray-200">{item.title}</p>
                  <div className="mt-0.5 flex items-center gap-2 text-[10px] text-gray-500">
                    <span>{item.source}</span>
                    <span>•</span>
                    <span>
                      {new Date(item.published).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                </div>
                <span
                  className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold ${styles.badge}`}
                >
                  {label}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
