/**
 * Liquidity Heatmap (Order Book Depth)
 * Visualises Binance L2 order book as a price ladder heatmap.
 * Large walls are highlighted as support/resistance reference levels.
 */

import { useState, useEffect, useCallback } from "react";

interface OrderBookLevel {
  price: number;
  quantity: number;
  side: "bid" | "ask";
}

interface OrderBookData {
  bids: [string, string][];
  asks: [string, string][];
  lastUpdateId: number;
}

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];
const DEPTH_LEVELS = 15;

function parseBook(raw: OrderBookData): OrderBookLevel[] {
  const levels: OrderBookLevel[] = [];
  raw.bids.slice(0, DEPTH_LEVELS).forEach(([p, q]) =>
    levels.push({ price: parseFloat(p), quantity: parseFloat(q), side: "bid" }),
  );
  raw.asks.slice(0, DEPTH_LEVELS).forEach(([p, q]) =>
    levels.push({ price: parseFloat(p), quantity: parseFloat(q), side: "ask" }),
  );
  return levels;
}

function wallIntensity(qty: number, maxQty: number): string {
  const ratio = maxQty > 0 ? qty / maxQty : 0;
  if (ratio >= 0.8) return "opacity-100";
  if (ratio >= 0.5) return "opacity-70";
  if (ratio >= 0.3) return "opacity-40";
  return "opacity-15";
}

export function LiquidityDepthHeatmap() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [book, setBook] = useState<OrderBookLevel[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchBook = useCallback(async () => {
    try {
      const resp = await fetch(
        `https://api.binance.com/api/v3/depth?symbol=${symbol}&limit=${DEPTH_LEVELS * 2}`,
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const raw = (await resp.json()) as OrderBookData;
      setBook(parseBook(raw));
      setError(false);
    } catch {
      setError(true);
    } finally {
      setIsLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    setIsLoading(true);
    void fetchBook();
    const interval = setInterval(() => void fetchBook(), 5_000);
    return () => { clearInterval(interval); };
  }, [fetchBook]);

  const bids = book.filter((l) => l.side === "bid").sort((a, b) => b.price - a.price);
  const asks = book.filter((l) => l.side === "ask").sort((a, b) => a.price - b.price);
  const maxBidQty = Math.max(...bids.map((b) => b.quantity), 1);
  const maxAskQty = Math.max(...asks.map((a) => a.quantity), 1);

  const midPrice = bids[0] && asks[0]
    ? (bids[0].price + asks[0].price) / 2
    : null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Liquidity Depth Heatmap</h2>
        <div className="flex items-center gap-2">
          {midPrice && (
            <span className="font-mono text-xs text-gray-400">
              ${midPrice.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
          )}
          <select
            value={symbol}
            onChange={(e) => { setSymbol(e.target.value); }}
            className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none"
            aria-label="Select symbol"
          >
            {SYMBOLS.map((s) => <option key={s} value={s}>{s.replace("USDT", "")}</option>)}
          </select>
        </div>
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        Live L2 order book. Bar width = order size relative to largest wall. Refreshes every 5s.
      </p>

      {error && <p className="mb-2 text-xs text-bearish">Order book unavailable.</p>}

      {isLoading ? (
        <div className="h-48 animate-pulse rounded bg-white/5" />
      ) : (
        <div className="grid grid-cols-2 gap-2 text-[9px]">
          {/* Asks (sell wall) — reversed so closest ask is at bottom */}
          <div>
            <p className="mb-1 text-center text-[9px] font-medium text-bearish">Asks (Sell)</p>
            <div className="flex flex-col-reverse gap-px">
              {asks.slice(0, DEPTH_LEVELS).map((level, i) => (
                <div key={i} className="relative flex items-center justify-between rounded-[1px] px-1.5 py-0.5 overflow-hidden">
                  <div
                    className={`absolute inset-0 bg-bearish/30 ${wallIntensity(level.quantity, maxAskQty)}`}
                    style={{ width: `${(level.quantity / maxAskQty) * 100}%` }}
                  />
                  <span className="relative text-gray-300 font-mono">
                    {level.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </span>
                  <span className="relative text-gray-500">{level.quantity.toFixed(3)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Bids (buy wall) */}
          <div>
            <p className="mb-1 text-center text-[9px] font-medium text-bullish">Bids (Buy)</p>
            <div className="flex flex-col gap-px">
              {bids.slice(0, DEPTH_LEVELS).map((level, i) => (
                <div key={i} className="relative flex items-center justify-between rounded-[1px] px-1.5 py-0.5 overflow-hidden">
                  <div
                    className={`absolute inset-0 bg-bullish/30 ${wallIntensity(level.quantity, maxBidQty)}`}
                    style={{ width: `${(level.quantity / maxBidQty) * 100}%` }}
                  />
                  <span className="relative text-gray-300 font-mono">
                    {level.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </span>
                  <span className="relative text-gray-500">{level.quantity.toFixed(3)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
