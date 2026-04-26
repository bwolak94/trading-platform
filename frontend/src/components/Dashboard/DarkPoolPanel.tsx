/**
 * Dark Pool / Block Trade Detector Panel
 * Scans recent aggTrades for unusually large institutional prints.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import axios from "axios";
import { fmtUSD, fmtPrice } from "../../lib/format";

interface BlockTrade {
  price: number;
  qty: number;
  notional_usd: number;
  side: "BUY" | "SELL";
  timestamp: number;
  sigma_from_mean: number;
}

interface DarkPoolData {
  symbol: string;
  block_count: number;
  mean_trade_usd: number;
  threshold_usd: number;
  institutional_bias: "BUY" | "SELL" | "NEUTRAL";
  buy_block_usd: number;
  sell_block_usd: number;
  total_block_usd: number;
  blocks: BlockTrade[];
}

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];

async function fetchDarkPool(symbol: string): Promise<DarkPoolData> {
  const { data } = await axios.get(`/api/v1/market/dark-pool/${symbol}`);
  return data.data as DarkPoolData;
}

export function DarkPoolPanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["dark-pool", symbol],
    queryFn: () => fetchDarkPool(symbol),
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: false,
  });

  const biasColor = data?.institutional_bias === "BUY" ? "text-bullish" : data?.institutional_bias === "SELL" ? "text-bearish" : "text-gray-400";

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Dark Pool Activity</h2>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none"
          aria-label="Select asset"
        >
          {SYMBOLS.map((s) => <option key={s} value={s}>{s.replace("USDT", "")}</option>)}
        </select>
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        Identifies prints ≥3σ above average trade size — potential institutional activity.
      </p>

      {isError && <p className="text-xs text-bearish mb-2">Block trade data unavailable</p>}

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-8 animate-pulse rounded bg-white/5" />)}
        </div>
      ) : data ? (
        <>
          <div className="mb-3 grid grid-cols-3 gap-2 text-center text-xs">
            <div className="rounded bg-background py-2">
              <p className="text-gray-500">Bias</p>
              <p className={`font-bold ${biasColor}`}>{data.institutional_bias}</p>
            </div>
            <div className="rounded bg-background py-2">
              <p className="text-gray-500">Block Vol</p>
              <p className="font-mono font-bold text-white">{fmtUSD(data.total_block_usd / 1e6, 1)}M</p>
            </div>
            <div className="rounded bg-background py-2">
              <p className="text-gray-500">Prints</p>
              <p className="font-mono font-bold text-amber-400">{data.block_count}</p>
            </div>
          </div>

          {/* Buy vs Sell bar */}
          {data.total_block_usd > 0 && (
            <div className="mb-3">
              <div className="mb-1 flex justify-between text-[10px] text-gray-500">
                <span>Buy {fmtUSD(data.buy_block_usd / 1e6, 1)}M</span>
                <span>Sell {fmtUSD(data.sell_block_usd / 1e6, 1)}M</span>
              </div>
              <div className="flex h-2 overflow-hidden rounded-full bg-bearish/40">
                <div
                  className="h-full bg-bullish"
                  style={{ width: `${(data.buy_block_usd / data.total_block_usd) * 100}%` }}
                />
              </div>
            </div>
          )}

          <div className="space-y-1 max-h-40 overflow-y-auto">
            {data.blocks.slice(0, 8).map((b, i) => (
              <div key={i} className="flex items-center justify-between text-[10px] rounded bg-background px-2 py-1">
                <span className={b.side === "BUY" ? "text-bullish font-semibold" : "text-bearish font-semibold"}>{b.side}</span>
                <span className="font-mono text-gray-300">{fmtPrice(b.price)}</span>
                <span className="font-mono text-white">{fmtUSD(b.notional_usd / 1e3, 0)}K</span>
                <span className="text-gray-500">{b.sigma_from_mean.toFixed(1)}σ</span>
                <span className="text-gray-600">{new Date(b.timestamp).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
