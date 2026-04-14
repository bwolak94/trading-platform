import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  fetchNews,
  fetchSentimentSnapshot,
  fetchWhaleData,
} from "../../api/client";
import type {
  NewsItemData,
  SentimentSnapshot,
  WhaleData,
} from "../../api/client";

type Tab = "news" | "sentiment" | "whales";

function SentimentBar({ value, width = "w-full" }: { value: number; width?: string }) {
  const pct = ((value + 1) / 2) * 100;
  const color = value > 0.1 ? "bg-green-500" : value < -0.1 ? "bg-red-500" : "bg-yellow-500";
  return (
    <div className={`${width} h-2 rounded-full bg-gray-700`} aria-label={`Sentiment: ${value}`}>
      <div className={`h-2 rounded-full ${color}`} style={{ width: `${Math.max(2, pct)}%` }} />
    </div>
  );
}

function BiasBadge({ bias }: { bias: string }) {
  const cls =
    bias === "LONG"
      ? "bg-green-500/20 text-green-400"
      : bias === "SHORT"
        ? "bg-red-500/20 text-red-400"
        : "bg-gray-500/20 text-gray-400";
  return <span className={`rounded px-2 py-0.5 text-xs font-bold ${cls}`}>{bias}</span>;
}

/* ─── News Feed Tab ─── */
function NewsFeedTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["intelligence-news"],
    queryFn: () => fetchNews(50),
    refetchInterval: 15_000,
  });

  if (isLoading) return <p className="p-4 text-gray-500">Loading news...</p>;
  const items: NewsItemData[] = data?.news ?? [];

  return (
    <div className="max-h-[480px] space-y-1 overflow-y-auto pr-1" aria-label="News feed list">
      {items.length === 0 && <p className="p-4 text-center text-gray-500">No news yet -- aggregator is warming up</p>}
      {items.map((item, idx) => (
        <a
          key={`${item.url}-${idx}`}
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-start gap-2 rounded p-2 hover:bg-white/5"
          aria-label={`News: ${item.title}`}
        >
          <span className="mt-0.5 shrink-0 rounded bg-gray-700 px-1.5 py-0.5 text-[10px] font-medium uppercase text-gray-300">
            {item.source.replace(/_/g, " ")}
          </span>
          <div className="min-w-0 flex-1">
            <p className={`text-xs leading-snug ${item.is_emergency ? "font-bold text-yellow-400" : "text-gray-200"}`}>
              {item.is_emergency && <span className="mr-1 text-red-400">[ALERT]</span>}
              {item.title}
            </p>
            <div className="mt-1 flex items-center gap-2">
              <SentimentBar value={item.sentiment} width="w-20" />
              <span className={`text-[10px] ${item.sentiment > 0 ? "text-green-400" : item.sentiment < 0 ? "text-red-400" : "text-gray-500"}`}>
                {item.sentiment > 0 ? "+" : ""}{item.sentiment.toFixed(2)}
              </span>
            </div>
          </div>
        </a>
      ))}
    </div>
  );
}

/* ─── Market Sentiment Tab ─── */
function SentimentTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["intelligence-sentiment"],
    queryFn: fetchSentimentSnapshot,
    refetchInterval: 15_000,
  });

  if (isLoading) return <p className="p-4 text-gray-500">Loading sentiment...</p>;
  const s: SentimentSnapshot | undefined = data;
  if (!s) return null;

  return (
    <div className="space-y-4 p-4" aria-label="Market sentiment overview">
      {/* Emergency banner */}
      {s.emergency_active && (
        <div className="rounded-lg border border-red-500/50 bg-red-500/10 p-3 text-center">
          <p className="text-sm font-bold text-red-400">EMERGENCY ACTIVE</p>
          <p className="mt-1 text-xs text-red-300">{s.emergency_reason}</p>
        </div>
      )}

      {/* Global sentiment */}
      <div>
        <p className="mb-1 text-xs font-medium uppercase text-gray-500">Global Sentiment</p>
        <div className="flex items-center gap-3">
          <SentimentBar value={s.global_sentiment} />
          <span className="text-sm font-bold text-white">{s.global_sentiment > 0 ? "+" : ""}{s.global_sentiment.toFixed(3)}</span>
        </div>
      </div>

      {/* Crypto vs Forex */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="mb-1 text-xs text-gray-500">Crypto</p>
          <div className="flex items-center gap-2">
            <SentimentBar value={s.crypto_sentiment} />
            <span className="text-xs text-gray-300">{s.crypto_sentiment.toFixed(3)}</span>
          </div>
        </div>
        <div>
          <p className="mb-1 text-xs text-gray-500">Forex</p>
          <div className="flex items-center gap-2">
            <SentimentBar value={s.forex_sentiment} />
            <span className="text-xs text-gray-300">{s.forex_sentiment.toFixed(3)}</span>
          </div>
        </div>
      </div>

      {/* Impact zones */}
      {s.impact_zones.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium uppercase text-gray-500">Impact Zones</p>
          <div className="flex flex-wrap gap-1">
            {s.impact_zones.map((zone) => (
              <span key={zone} className="rounded bg-gray-700 px-2 py-0.5 text-xs text-gray-300">{zone}</span>
            ))}
          </div>
        </div>
      )}

      {/* Priority alerts */}
      {s.priority_alerts.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium uppercase text-gray-500">Priority Alerts</p>
          <ul className="space-y-1">
            {s.priority_alerts.map((alert, i) => (
              <li key={i} className="text-xs text-yellow-400">{alert}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[10px] text-gray-600">Tracking {s.news_count} articles</p>
    </div>
  );
}

/* ─── Whale Monitor Tab ─── */
function WhaleTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["intelligence-whales"],
    queryFn: fetchWhaleData,
    refetchInterval: 15_000,
  });

  if (isLoading) return <p className="p-4 text-gray-500">Loading whale data...</p>;
  const w: WhaleData | undefined = data;
  if (!w) return null;

  const symbols = Object.keys(w.long_short_ratios);

  return (
    <div className="space-y-4 p-4" aria-label="Whale monitor data">
      {symbols.length === 0 && <p className="text-center text-xs text-gray-500">Waiting for data...</p>}

      {symbols.map((sym) => {
        const ls = w.long_short_ratios[sym];
        if (!ls) return null;
        const oi = w.open_interest[sym];
        const retail = w.retail_sentiment[sym];
        return (
          <div key={sym} className="rounded-lg border border-border bg-surface p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-bold text-white">{sym}</span>
              <BiasBadge bias={ls.bias} />
            </div>

            {/* Long/Short bar */}
            <div className="mb-2">
              <div className="mb-0.5 flex justify-between text-[10px] text-gray-400">
                <span>Long {ls.long_pct}%</span>
                <span>Short {ls.short_pct}%</span>
              </div>
              <div className="flex h-3 overflow-hidden rounded-full">
                <div className="bg-green-500" style={{ width: `${ls.long_pct}%` }} />
                <div className="bg-red-500" style={{ width: `${ls.short_pct}%` }} />
              </div>
            </div>

            {/* OI + Retail */}
            <div className="flex justify-between text-[10px] text-gray-400">
              {oi !== undefined && <span>OI: {oi.toLocaleString()}</span>}
              {retail !== undefined && <span>Retail Long: {retail}%</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ─── Main Panel ─── */
export function IntelligencePanel() {
  const [tab, setTab] = useState<Tab>("news");

  const tabs: { key: Tab; label: string }[] = [
    { key: "news", label: "News Feed" },
    { key: "sentiment", label: "Sentiment" },
    { key: "whales", label: "Whale Monitor" },
  ];

  return (
    <section className="rounded-lg border border-border bg-surface" aria-label="Market Intelligence Panel">
      <div className="flex border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`flex-1 py-2.5 text-xs font-medium transition-colors ${
              tab === t.key
                ? "border-b-2 border-accent text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
            aria-label={`${t.label} tab`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "news" && <NewsFeedTab />}
      {tab === "sentiment" && <SentimentTab />}
      {tab === "whales" && <WhaleTab />}
    </section>
  );
}
