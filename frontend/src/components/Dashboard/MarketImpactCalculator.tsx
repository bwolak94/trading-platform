/**
 * B12: Market Impact Calculator
 *
 * Input: order size in USD.
 * Output: estimated slippage % based on current order book depth.
 */

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useDebounce } from "../hooks/useDebounce";

interface OrderBookDepth {
  bids: [number, number][];  // [price, size]
  asks: [number, number][];
}

interface ImpactEstimate {
  order_usd: number;
  slippage_pct: number;
  filled_at_avg: number;
  market_price: number;
  liquidity_available_usd: number;
}

async function fetchOrderBook(symbol: string): Promise<OrderBookDepth> {
  const resp = await fetch(`/api/v1/market/orderbook?symbol=${symbol}&limit=50`);
  if (!resp.ok) throw new Error("Failed to fetch order book");
  return resp.json();
}

function estimateImpact(
  orderUsd: number,
  side: "BUY" | "SELL",
  book: OrderBookDepth,
): ImpactEstimate {
  const levels = side === "BUY" ? book.asks : book.bids;
  if (!levels.length) {
    return { order_usd: orderUsd, slippage_pct: 0, filled_at_avg: 0, market_price: 0, liquidity_available_usd: 0 };
  }

  const marketPrice = levels[0]?.[0] ?? 0;
  let remaining = orderUsd;
  let totalCost = 0;
  let totalQty = 0;
  let liquidityUsd = 0;

  for (const [price, qty] of levels) {
    const levelUsd = price * qty;
    liquidityUsd += levelUsd;
    if (remaining <= 0) break;
    const take = Math.min(remaining, levelUsd);
    const takenQty = take / price;
    totalCost += takenQty * price;
    totalQty += takenQty;
    remaining -= take;
  }

  const avgFill = totalQty > 0 ? totalCost / totalQty : marketPrice;
  const slippage = marketPrice > 0 ? Math.abs(avgFill - marketPrice) / marketPrice * 100 : 0;

  return {
    order_usd: orderUsd,
    slippage_pct: slippage,
    filled_at_avg: avgFill,
    market_price: marketPrice,
    liquidity_available_usd: liquidityUsd,
  };
}

export function MarketImpactCalculator() {
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [orderUsd, setOrderUsd] = useState<string>("10000");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");

  const debouncedUsd = useDebounce(parseFloat(orderUsd) || 0, 400);

  const { data: book, isLoading } = useQuery({
    queryKey: ["orderbook-impact", symbol],
    queryFn: () => fetchOrderBook(symbol),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const impact = useMemo(() => {
    if (!book || debouncedUsd <= 0) return null;
    return estimateImpact(debouncedUsd, side, book);
  }, [book, debouncedUsd, side]);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold text-gray-200">Market Impact Calculator</h3>
      <p className="mb-3 text-xs text-gray-400">
        Estimate slippage for a given order size based on live order book depth.
      </p>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div>
          <label className="mb-1 block text-xs text-gray-500" htmlFor="impact-symbol">Asset</label>
          <select
            id="impact-symbol"
            value={symbol}
            onChange={(e) => { setSymbol(e.target.value); }}
            className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs text-gray-300"
          >
            <option value="BTC/USDT">BTC/USDT</option>
            <option value="ETH/USDT">ETH/USDT</option>
            <option value="SOL/USDT">SOL/USDT</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500" htmlFor="impact-side">Side</label>
          <select
            id="impact-side"
            value={side}
            onChange={(e) => { setSide(e.target.value as "BUY" | "SELL"); }}
            className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs text-gray-300"
          >
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </div>
        <div className="col-span-2">
          <label className="mb-1 block text-xs text-gray-500" htmlFor="impact-size">
            Order Size (USD)
          </label>
          <input
            id="impact-size"
            type="number"
            min="100"
            step="1000"
            value={orderUsd}
            onChange={(e) => { setOrderUsd(e.target.value); }}
            className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs text-gray-300"
            placeholder="10000"
          />
        </div>
      </div>

      {isLoading && (
        <div className="text-center text-xs text-gray-500">Fetching order book…</div>
      )}

      {impact && (
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded bg-background/60 p-3 text-center">
            <div className="text-xs text-gray-500">Est. Slippage</div>
            <div className={`text-lg font-bold ${impact.slippage_pct < 0.1 ? "text-bullish" : impact.slippage_pct < 0.5 ? "text-amber-400" : "text-bearish"}`}>
              {impact.slippage_pct.toFixed(3)}%
            </div>
          </div>
          <div className="rounded bg-background/60 p-3 text-center">
            <div className="text-xs text-gray-500">Avg Fill</div>
            <div className="text-lg font-bold font-mono text-gray-200">
              ${impact.filled_at_avg.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </div>
          </div>
          <div className="col-span-2 rounded bg-background/60 p-3 text-center">
            <div className="text-xs text-gray-500">Available Liquidity in Book</div>
            <div className="text-sm font-semibold text-gray-300">
              ${(impact.liquidity_available_usd / 1000).toFixed(1)}K
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
