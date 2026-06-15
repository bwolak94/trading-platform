/**
 * Multi-Exchange Price Aggregator Panel
 * Binance vs Bybit vs OKX prices for the same asset,
 * showing spread and premium/discount.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import axios from "axios";
import { fmtPrice } from "../../lib/format";

interface ExchangePrice {
  exchange: string;
  price: number;
  premium_pct: number;
}

interface MultiExchangeData {
  symbol: string;
  prices: ExchangePrice[];
  spread_usd: number;
  spread_pct: number;
  reference_exchange: string;
}

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];

async function fetchMultiExchange(symbol: string): Promise<MultiExchangeData> {
  const { data } = await axios.get(`/api/v1/market/multi-exchange/${symbol}`);
  return data.data as MultiExchangeData;
}

const EXCHANGE_COLOR: Record<string, string> = {
  Binance: "text-yellow-400",
  Bybit:   "text-orange-400",
  OKX:     "text-blue-400",
};

export function MultiExchangePanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["multi-exchange", symbol],
    queryFn: () => fetchMultiExchange(symbol),
    refetchInterval: 15_000,
    staleTime: 10_000,
    retry: false,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Multi-Exchange Prices</h2>
        <select
          value={symbol}
          onChange={(e) => { setSymbol(e.target.value); }}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none"
          aria-label="Select asset"
        >
          {SYMBOLS.map((s) => <option key={s} value={s}>{s.replace("USDT", "")}</option>)}
        </select>
      </div>

      {isError && <p className="text-xs text-bearish mb-2">Price data unavailable</p>}

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-12 animate-pulse rounded bg-white/5" />)}
        </div>
      ) : data ? (
        <>
          <div className="mb-3 space-y-2">
            {data.prices.map((p) => (
              <div key={p.exchange} className="flex items-center justify-between rounded border border-border bg-background px-3 py-2">
                <span className={`text-xs font-semibold ${EXCHANGE_COLOR[p.exchange] ?? "text-gray-300"}`}>
                  {p.exchange}
                </span>
                <span className="font-mono text-sm text-white">{fmtPrice(p.price)}</span>
                <span className={`text-xs font-mono ${p.premium_pct > 0 ? "text-bullish" : p.premium_pct < 0 ? "text-bearish" : "text-gray-500"}`}>
                  {p.premium_pct >= 0 ? "+" : ""}{p.premium_pct.toFixed(4)}%
                </span>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2 text-center text-xs">
            <div className="rounded bg-background py-1.5">
              <p className="text-gray-500">Spread $</p>
              <p className="font-mono font-bold text-amber-400">{fmtPrice(data.spread_usd)}</p>
            </div>
            <div className="rounded bg-background py-1.5">
              <p className="text-gray-500">Spread %</p>
              <p className="font-mono font-bold text-amber-400">{data.spread_pct.toFixed(4)}%</p>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
