/**
 * Watchlist with Price Alerts
 * Persisted to localStorage. Fetches live prices every 10s.
 * Fires a visual alert when a target is breached.
 */

import { useEffect, useReducer, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { fmtPrice, fmtPct, colorClass } from "../../lib/format";

interface WatchlistEntry {
  id: string;
  symbol: string;
  targetPrice: number;
  direction: "above" | "below";
  triggered: boolean;
  addedAt: number;
}

interface PriceTick {
  symbol: string;
  price: number;
  change24h: number;
}

const LS_KEY = "trading_watchlist_v1";

function loadEntries(): WatchlistEntry[] {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) ?? "[]") as WatchlistEntry[];
  } catch {
    return [];
  }
}

function saveEntries(entries: WatchlistEntry[]) {
  localStorage.setItem(LS_KEY, JSON.stringify(entries));
}

type Action =
  | { type: "add"; entry: WatchlistEntry }
  | { type: "remove"; id: string }
  | { type: "trigger"; id: string }
  | { type: "reset"; id: string };

function reducer(state: WatchlistEntry[], action: Action): WatchlistEntry[] {
  let next: WatchlistEntry[];
  switch (action.type) {
    case "add":
      next = [...state, action.entry];
      break;
    case "remove":
      next = state.filter((e) => e.id !== action.id);
      break;
    case "trigger":
      next = state.map((e) => e.id === action.id ? { ...e, triggered: true } : e);
      break;
    case "reset":
      next = state.map((e) => e.id === action.id ? { ...e, triggered: false } : e);
      break;
    default:
      return state;
  }
  saveEntries(next);
  return next;
}

async function fetchPriceTick(symbol: string): Promise<PriceTick> {
  const { data } = await axios.get<{ candles?: { close: number }[]; data?: { close: number }[] }>(
    `/api/v1/market/ohlcv?symbol=${symbol}&timeframe=1d&limit=2`,
  );
  const candles = data.candles ?? data.data ?? [];
  const current = candles[candles.length - 1]?.close ?? 0;
  const prev = candles[0]?.close ?? current;
  const change24h = prev > 0 ? ((current - prev) / prev) * 100 : 0;
  return { symbol, price: current, change24h };
}

function PriceCell({ symbol }: { symbol: string }) {
  const { data } = useQuery({
    queryKey: ["watchlist-price", symbol],
    queryFn: () => fetchPriceTick(symbol),
    refetchInterval: 10_000,
    retry: false,
    staleTime: 5_000,
  });

  if (!data) return <span className="text-gray-600 font-mono text-xs">…</span>;
  return (
    <div className="text-right">
      <p className="font-mono text-xs text-white">{fmtPrice(data.price)}</p>
      <p className={`font-mono text-[10px] ${colorClass(data.change24h)}`}>
        {fmtPct(data.change24h, { showSign: true, decimals: 2 })}
      </p>
    </div>
  );
}

const POPULAR = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"];

export function WatchlistPanel() {
  const [entries, dispatch] = useReducer(reducer, undefined, loadEntries);
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [customSymbol, setCustomSymbol] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [direction, setDirection] = useState<"above" | "below">("above");
  const alertedRef = useRef<Set<string>>(new Set());

  // Check price alerts
  useEffect(() => {
    const untriggered = entries.filter((e) => !e.triggered);
    if (untriggered.length === 0) return;

    const check = async () => {
      for (const entry of untriggered) {
        if (alertedRef.current.has(entry.id)) continue;
        try {
          const tick = await fetchPriceTick(entry.symbol);
          const hit =
            (entry.direction === "above" && tick.price >= entry.targetPrice) ||
            (entry.direction === "below" && tick.price <= entry.targetPrice);
          if (hit) {
            dispatch({ type: "trigger", id: entry.id });
            alertedRef.current.add(entry.id);
          }
        } catch {
          // ignore
        }
      }
    };

    void check();
    const interval = setInterval(() => void check(), 15_000);
    return () => clearInterval(interval);
  }, [entries]);

  const handleAdd = () => {
    const sym = (customSymbol.trim() || symbol).toUpperCase().replace("/", "");
    const price = parseFloat(targetPrice);
    if (!sym || isNaN(price) || price <= 0) return;
    dispatch({
      type: "add",
      entry: {
        id: `${sym}-${Date.now()}`,
        symbol: sym,
        targetPrice: price,
        direction,
        triggered: false,
        addedAt: Date.now(),
      },
    });
    setTargetPrice("");
    setCustomSymbol("");
  };

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-4 text-sm font-semibold text-white">Watchlist & Price Alerts</h2>

      {/* Add new alert */}
      <div className="mb-4 space-y-2">
        <div className="flex gap-2">
          <select
            value={symbol}
            onChange={(e) => { setSymbol(e.target.value); setCustomSymbol(""); }}
            className="flex-1 rounded border border-border bg-background px-2 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent"
            aria-label="Select preset symbol"
          >
            {POPULAR.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <input
            value={customSymbol}
            onChange={(e) => setCustomSymbol(e.target.value.toUpperCase())}
            placeholder="or type: LINKUSDT"
            className="flex-1 rounded border border-border bg-background px-2 py-1.5 text-xs text-gray-300 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-accent"
            aria-label="Custom symbol"
          />
        </div>
        <div className="flex gap-2">
          <select
            value={direction}
            onChange={(e) => setDirection(e.target.value as "above" | "below")}
            className="rounded border border-border bg-background px-2 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent"
            aria-label="Alert direction"
          >
            <option value="above">Price rises above</option>
            <option value="below">Price drops below</option>
          </select>
          <input
            value={targetPrice}
            onChange={(e) => setTargetPrice(e.target.value)}
            placeholder="Target price $"
            type="number"
            className="flex-1 rounded border border-border bg-background px-2 py-1.5 font-mono text-xs text-gray-300 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-accent"
            aria-label="Target price"
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          />
          <button
            type="button"
            onClick={handleAdd}
            className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent/80 transition-colors"
            aria-label="Add alert"
          >
            Add
          </button>
        </div>
      </div>

      {/* Entries */}
      {entries.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-600">No alerts set. Add one above.</p>
      ) : (
        <div className="space-y-2">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className={`flex items-center justify-between rounded border px-3 py-2 text-xs ${
                entry.triggered
                  ? "border-bullish/40 bg-bullish/10"
                  : "border-border bg-background"
              }`}
              role="listitem"
            >
              <div className="flex flex-col gap-0.5">
                <span className="font-medium text-gray-200">{entry.symbol}</span>
                <span className="text-gray-500">
                  {entry.direction === "above" ? "≥" : "≤"} {fmtPrice(entry.targetPrice)}
                </span>
              </div>

              <PriceCell symbol={entry.symbol} />

              <div className="flex items-center gap-2">
                {entry.triggered && (
                  <span className="rounded bg-bullish/20 px-1.5 py-0.5 text-[10px] font-bold text-bullish">
                    HIT
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => dispatch({ type: "remove", id: entry.id })}
                  className="rounded p-1 text-gray-600 hover:text-bearish transition-colors"
                  aria-label={`Remove ${entry.symbol} alert`}
                >
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
