import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchOrderBook, type OrderBookData } from "../../api/client";

interface OrderBookDepthProps {
  asset: string;
  limit?: number;
}

interface ParsedLevel {
  price: number;
  qty: number;
  total: number;
}

function parseLevels(raw: [string, string][]): ParsedLevel[] {
  let cumulative = 0;
  return raw.map(([price, qty]) => {
    const q = parseFloat(qty);
    cumulative += q;
    return { price: parseFloat(price), qty: q, total: cumulative };
  });
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (price >= 1) return price.toFixed(4);
  return price.toFixed(6);
}

function formatQty(qty: number): string {
  if (qty >= 1000) return `${(qty / 1000).toFixed(1)}k`;
  if (qty >= 1) return qty.toFixed(3);
  return qty.toFixed(5);
}

const MAX_ROWS = 15;

export function OrderBookDepth({ asset, limit = 100 }: OrderBookDepthProps) {
  const [data, setData] = useState<OrderBookData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const binanceSymbol = asset.replace("/", "").toUpperCase();

  const loadData = useCallback(async (isInitial: boolean) => {
    try {
      if (isInitial) setLoading(true);
      const result = await fetchOrderBook(binanceSymbol, limit);
      setData(result);
      setError(null);
    } catch {
      if (isInitial) setError("Failed to load order book");
    } finally {
      if (isInitial) setLoading(false);
    }
  }, [binanceSymbol, limit]);

  useEffect(() => {
    let cancelled = false;

    loadData(true);

    const timer = setInterval(() => {
      if (!cancelled) loadData(false);
    }, 5000);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [loadData]);

  const { bids, asks, maxQty } = useMemo(() => {
    if (!data) return { bids: [], asks: [], maxQty: 0 };

    const parsedBids = parseLevels(data.bids).slice(0, MAX_ROWS);
    const parsedAsks = parseLevels(data.asks).slice(0, MAX_ROWS);

    const allQty = [...parsedBids, ...parsedAsks].map((l) => l.qty);
    const max = Math.max(...allQty, 0.001);

    return { bids: parsedBids, asks: parsedAsks, maxQty: max };
  }, [data]);

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-surface p-4">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
          Order Book
        </h3>
        <div className="flex items-center gap-2 py-4 text-xs text-gray-400">
          <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading order book...
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-lg border border-border bg-surface p-4">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
          Order Book
        </h3>
        <p className="py-4 text-xs text-red-400">{error ?? "No data available"}</p>
      </div>
    );
  }

  const spreadPct = data.best_bid > 0
    ? ((data.spread / data.best_bid) * 100).toFixed(3)
    : "0.000";

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-medium uppercase tracking-wide text-gray-500">
          Order Book
        </h3>
        <span className="flex items-center gap-1 text-xs text-gray-500">
          <span className="h-1.5 w-1.5 rounded-full bg-bullish animate-pulse" />
          5s
        </span>
      </div>

      {/* Column headers */}
      <div className="mb-1 grid grid-cols-3 text-[10px] text-gray-500">
        <span>Qty</span>
        <span className="text-center">Price</span>
        <span className="text-right">Qty</span>
      </div>

      {/* Asks (reversed so lowest ask is at bottom, near spread) */}
      <div className="space-y-px" role="list" aria-label="Ask levels">
        {asks.slice(0, MAX_ROWS).reverse().map((level) => (
          <LevelRow
            key={`ask-${level.price}`}
            price={level.price}
            qty={level.qty}
            maxQty={maxQty}
            side="ask"
          />
        ))}
      </div>

      {/* Spread */}
      <div className="my-1.5 flex items-center justify-center gap-2 rounded bg-background px-2 py-1">
        <span className="text-[10px] text-gray-500">Spread</span>
        <span className="font-mono text-xs font-bold text-white">
          {formatPrice(data.spread)}
        </span>
        <span className="text-[10px] text-gray-500">({spreadPct}%)</span>
      </div>

      {/* Bids */}
      <div className="space-y-px" role="list" aria-label="Bid levels">
        {bids.slice(0, MAX_ROWS).map((level) => (
          <LevelRow
            key={`bid-${level.price}`}
            price={level.price}
            qty={level.qty}
            maxQty={maxQty}
            side="bid"
          />
        ))}
      </div>

      {/* Summary footer */}
      <div className="mt-3 flex items-center justify-between text-[10px] text-gray-500">
        <span>
          Bid vol:{" "}
          <span className="font-mono text-bullish">
            {formatQty(bids.reduce((s, l) => s + l.qty, 0))}
          </span>
        </span>
        <span>
          Ask vol:{" "}
          <span className="font-mono text-bearish">
            {formatQty(asks.reduce((s, l) => s + l.qty, 0))}
          </span>
        </span>
      </div>
    </div>
  );
}

interface LevelRowProps {
  price: number;
  qty: number;
  maxQty: number;
  side: "bid" | "ask";
}

function LevelRow({ price, qty, maxQty, side }: LevelRowProps) {
  const pct = Math.min((qty / maxQty) * 100, 100);
  const isBid = side === "bid";

  return (
    <div className="relative grid grid-cols-3 items-center py-0.5 text-xs" role="listitem">
      {/* Background bar */}
      <div
        className={`absolute inset-y-0 ${isBid ? "left-0" : "right-0"} ${
          isBid ? "bg-bullish/10" : "bg-bearish/10"
        } rounded-sm`}
        style={{ width: `${pct}%` }}
      />

      {/* Bid qty (left column) */}
      <span className={`relative font-mono ${isBid ? "text-bullish" : "text-transparent"}`}>
        {isBid ? formatQty(qty) : ""}
      </span>

      {/* Price (center) */}
      <span className="relative text-center font-mono text-gray-300">
        {formatPrice(price)}
      </span>

      {/* Ask qty (right column) */}
      <span className={`relative text-right font-mono ${!isBid ? "text-bearish" : "text-transparent"}`}>
        {!isBid ? formatQty(qty) : ""}
      </span>
    </div>
  );
}
