import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  fetchLongShortRatio,
  fetchNewsVelocity,
  fetchStablecoinRatio,
} from "../../api/client";
import type {
  LongShortData,
  NewsVelocityData,
  StablecoinRatioData,
} from "../../api/client";

/* ── Session indicator (extracted from SessionClock logic) ─────────── */

interface Session {
  name: string;
  short: string;
  openHourUTC: number;
  closeHourUTC: number;
  color: string;
  bgColor: string;
}

const SESSIONS: Session[] = [
  { name: "Asian",    short: "AS", openHourUTC: 0,  closeHourUTC: 9,  color: "text-yellow-400", bgColor: "bg-yellow-400/15 border-yellow-400/30" },
  { name: "London",   short: "LN", openHourUTC: 8,  closeHourUTC: 17, color: "text-blue-400",   bgColor: "bg-blue-400/15 border-blue-400/30"   },
  { name: "New York", short: "NY", openHourUTC: 13, closeHourUTC: 22, color: "text-green-400",  bgColor: "bg-green-400/15 border-green-400/30"  },
];

function isSessionActive(s: Session, utcHour: number): boolean {
  if (s.openHourUTC < s.closeHourUTC) {
    return utcHour >= s.openHourUTC && utcHour < s.closeHourUTC;
  }
  return utcHour >= s.openHourUTC || utcHour < s.closeHourUTC;
}

function SessionIndicator() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  const utcHour = now.getUTCHours();

  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Active trading sessions">
      {SESSIONS.map((s) => {
        const active = isSessionActive(s, utcHour);
        return (
          <div
            key={s.name}
            className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium transition-all duration-300 ${
              active ? `${s.bgColor} ${s.color}` : "border-border/30 text-muted-foreground/40"
            }`}
            title={`${s.name}: ${s.openHourUTC}:00–${s.closeHourUTC}:00 UTC`}
            aria-label={`${s.name} session ${active ? "open" : "closed"}`}
          >
            {active && (
              <span
                className={`h-1.5 w-1.5 rounded-full animate-pulse ${s.color.replace("text-", "bg-")}`}
                aria-hidden="true"
              />
            )}
            {s.short}
          </div>
        );
      })}
    </div>
  );
}

/* ── Sentiment badge helpers ───────────────────────────────────────── */

function sentimentLabel(s: LongShortData["sentiment"]): string {
  switch (s) {
    case "extreme_long":  return "Extreme Long";
    case "long":          return "Long Bias";
    case "neutral":       return "Neutral";
    case "short":         return "Short Bias";
    case "extreme_short": return "Extreme Short";
  }
}

function sentimentBadgeClass(s: LongShortData["sentiment"]): string {
  switch (s) {
    case "extreme_long":  return "bg-green-500/20 text-green-400 border-green-500/40";
    case "long":          return "bg-green-500/10 text-green-300 border-green-400/30";
    case "neutral":       return "bg-gray-500/15 text-gray-300 border-gray-500/30";
    case "short":         return "bg-red-500/10 text-red-300 border-red-400/30";
    case "extreme_short": return "bg-red-500/20 text-red-400 border-red-500/40";
  }
}

function longShortLineColor(ratio: number): string {
  if (ratio > 2.0) return "#f87171"; // red-400
  if (ratio < 1.5) return "#4ade80"; // green-400
  return "#facc15"; // yellow-400
}

/* ── SSR signal color ──────────────────────────────────────────────── */

function ssrSignalClass(signal: StablecoinRatioData["signal"]): string {
  switch (signal) {
    case "bullish":         return "text-green-400";
    case "neutral_bullish": return "text-green-300";
    case "neutral":         return "text-gray-300";
    case "bearish":         return "text-red-400";
    default:                return "text-gray-400";
  }
}

function formatLargeNumber(n: number): string {
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toFixed(0)}`;
}

/* ── Panel ─────────────────────────────────────────────────────────── */

export function MarketSentimentPanel() {
  const { data: lsData, isLoading: lsLoading } = useQuery<LongShortData>({
    queryKey: ["long-short-ratio", "BTCUSDT"],
    queryFn: () => fetchLongShortRatio("BTCUSDT"),
    refetchInterval: 60_000,
  });

  const { data: newsData, isLoading: newsLoading } = useQuery<NewsVelocityData>({
    queryKey: ["news-velocity"],
    queryFn: fetchNewsVelocity,
    refetchInterval: 300_000,
  });

  const { data: ssrData, isLoading: ssrLoading } = useQuery<StablecoinRatioData>({
    queryKey: ["stablecoin-ratio"],
    queryFn: fetchStablecoinRatio,
    refetchInterval: 300_000,
  });

  const chartData = lsData?.data.map((p) => ({
    t: p.timestamp,
    ratio: parseFloat(p.long_short_ratio.toFixed(3)),
  })) ?? [];

  const currentRatio = lsData?.current_ratio ?? 0;
  const lineColor = longShortLineColor(currentRatio);
  const topVelocity = newsData?.velocity.slice(0, 5) ?? [];
  const maxCount = topVelocity[0]?.count ?? 1;

  return (
    <div className="rounded-lg border border-border bg-surface p-4 space-y-4" aria-label="Market Sentiment Panel">
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400">
          Market Sentiment
        </h3>
        <SessionIndicator />
      </div>

      {/* Long / Short Ratio — BTCUSDT */}
      <section aria-label="Long Short Ratio">
        <div className="mb-1 flex items-center justify-between">
          <span className="text-xs font-medium text-gray-300">BTC L/S Ratio</span>
          {lsLoading ? (
            <span className="h-4 w-16 animate-pulse rounded bg-border/50" />
          ) : lsData ? (
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-sm font-semibold" style={{ color: lineColor }}>
                {currentRatio.toFixed(2)}
              </span>
              <span
                className={`rounded border px-1.5 py-0.5 text-xs font-medium ${sentimentBadgeClass(lsData.sentiment)}`}
                aria-label={`Current sentiment: ${sentimentLabel(lsData.sentiment)}`}
              >
                {sentimentLabel(lsData.sentiment)}
              </span>
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">N/A</span>
          )}
        </div>

        {/* Sparkline */}
        <div className="h-[60px] w-full" aria-hidden="true">
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={60}>
              <LineChart data={chartData} margin={{ top: 4, right: 0, left: 0, bottom: 4 }}>
                <Line
                  type="monotone"
                  dataKey="ratio"
                  stroke={lineColor}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
                <Tooltip
                  contentStyle={{ background: "#1c1c2e", border: "1px solid #2a2a3d", borderRadius: 6, fontSize: 11 }}
                  labelFormatter={() => ""}
                  formatter={(value: number) => [value.toFixed(3), "L/S Ratio"]}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
              {lsLoading ? "Loading..." : "No data"}
            </div>
          )}
        </div>
      </section>

      {/* Stablecoin Supply Ratio */}
      <section aria-label="Stablecoin Supply Ratio" className="border-t border-border/40 pt-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-medium text-gray-300">Stablecoin SSR</span>
          {ssrLoading ? (
            <span className="h-4 w-20 animate-pulse rounded bg-border/50" />
          ) : ssrData ? (
            <span className={`font-mono text-sm font-semibold ${ssrSignalClass(ssrData.signal)}`}>
              {(ssrData.ssr * 100).toFixed(2)}%
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">N/A</span>
          )}
        </div>
        {!ssrLoading && ssrData && (
          <div className="space-y-0.5">
            <p className={`text-xs ${ssrSignalClass(ssrData.signal)}`}>{ssrData.interpretation}</p>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span>USDT {formatLargeNumber(ssrData.usdt_market_cap)}</span>
              <span>USDC {formatLargeNumber(ssrData.usdc_market_cap)}</span>
            </div>
          </div>
        )}
      </section>

      {/* News Velocity */}
      <section aria-label="News Velocity" className="border-t border-border/40 pt-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-gray-300">News Velocity</span>
          {!newsLoading && newsData && (
            <span className="text-xs text-muted-foreground">
              {newsData.total_articles} articles scanned
            </span>
          )}
        </div>

        {newsLoading ? (
          <div className="space-y-1.5">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-5 animate-pulse rounded bg-border/40" />
            ))}
          </div>
        ) : topVelocity.length === 0 ? (
          <p className="text-xs text-muted-foreground">No news data available</p>
        ) : (
          <ul className="space-y-1.5" aria-label="Top mentioned symbols in news">
            {topVelocity.map(({ symbol, count }) => (
              <li key={symbol} className="flex items-center gap-2">
                {/* Symbol chip */}
                <span className="w-10 rounded bg-accent/10 px-1 py-0.5 text-center text-xs font-bold text-accent">
                  {symbol}
                </span>
                {/* Heat bar */}
                <div
                  className="h-3 flex-1 overflow-hidden rounded-full bg-border/40"
                  role="progressbar"
                  aria-valuenow={count}
                  aria-valuemax={maxCount}
                  aria-label={`${symbol}: ${count} articles`}
                >
                  <div
                    className="h-full rounded-full bg-accent/60 transition-all duration-500"
                    style={{ width: `${(count / maxCount) * 100}%` }}
                  />
                </div>
                {/* Article count */}
                <span className="w-5 text-right font-mono text-xs text-gray-400">
                  {count}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
