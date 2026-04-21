import { useQuery } from "@tanstack/react-query";
import { fetchBtcDominance, fetchMarketBreadth, fetchFearGreed } from "../../api/client";

function ProgressBar({ value, max = 100, colorClass }: { value: number; max?: number; colorClass: string }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="h-1.5 w-full rounded-full bg-border/50 overflow-hidden">
      <div className={`h-full rounded-full transition-all duration-500 ${colorClass}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function formatLargeNumber(n: number): string {
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toFixed(0)}`;
}

function getFearGreedColor(value: number): string {
  if (value <= 25) return "text-red-400";
  if (value <= 45) return "text-orange-400";
  if (value <= 55) return "text-yellow-400";
  if (value <= 75) return "text-green-300";
  return "text-green-400";
}

export function MarketOverviewPanel() {
  const { data: dominance } = useQuery({
    queryKey: ["btc-dominance"],
    queryFn: fetchBtcDominance,
    refetchInterval: 5 * 60_000,
  });

  const { data: breadth } = useQuery({
    queryKey: ["market-breadth"],
    queryFn: fetchMarketBreadth,
    refetchInterval: 5 * 60_000,
  });

  const { data: fng } = useQuery({
    queryKey: ["fear-greed"],
    queryFn: fetchFearGreed,
    refetchInterval: 5 * 60_000,
  });

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      <h2 className="text-base font-semibold text-foreground">Market Overview</h2>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {/* Fear & Greed */}
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Fear & Greed</span>
          {fng ? (
            <>
              <span className={`text-xl font-bold ${getFearGreedColor(fng.value)}`}>{fng.value}</span>
              <span className={`text-xs ${getFearGreedColor(fng.value)}`}>{fng.value_classification}</span>
            </>
          ) : (
            <span className="text-sm text-muted-foreground">—</span>
          )}
        </div>

        {/* BTC Dominance */}
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">BTC Dominance</span>
          {dominance ? (
            <>
              <span className="text-xl font-bold text-foreground">{dominance.btc_dominance.toFixed(1)}%</span>
              <span className={`text-xs ${dominance.market_cap_change_24h_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                {dominance.market_cap_change_24h_pct >= 0 ? "+" : ""}{dominance.market_cap_change_24h_pct.toFixed(2)}% 24h
              </span>
            </>
          ) : (
            <span className="text-sm text-muted-foreground">—</span>
          )}
        </div>

        {/* Total Market Cap */}
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Total Market Cap</span>
          {dominance ? (
            <>
              <span className="text-xl font-bold text-foreground">{formatLargeNumber(dominance.total_market_cap_usd)}</span>
              <span className="text-xs text-muted-foreground">{formatLargeNumber(dominance.total_volume_24h_usd)} 24h vol</span>
            </>
          ) : (
            <span className="text-sm text-muted-foreground">—</span>
          )}
        </div>

        {/* Active Coins */}
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Active Coins</span>
          {dominance ? (
            <span className="text-xl font-bold text-foreground">{dominance.active_cryptocurrencies.toLocaleString()}</span>
          ) : (
            <span className="text-sm text-muted-foreground">—</span>
          )}
        </div>
      </div>

      {/* Market Breadth */}
      {breadth && (
        <div className="flex flex-col gap-2 pt-2 border-t border-border/50">
          <span className="text-xs font-medium text-muted-foreground">
            Market Breadth — {breadth.scanned_symbols} pairs scanned
          </span>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="w-16 text-xs text-muted-foreground">EMA 20</span>
              <div className="flex-1">
                <ProgressBar
                  value={breadth.above_ema20_pct}
                  colorClass={breadth.above_ema20_pct > 60 ? "bg-green-400" : breadth.above_ema20_pct > 40 ? "bg-yellow-400" : "bg-red-400"}
                />
              </div>
              <span className={`w-10 text-right text-xs font-medium ${breadth.above_ema20_pct > 60 ? "text-green-400" : breadth.above_ema20_pct > 40 ? "text-yellow-400" : "text-red-400"}`}>
                {breadth.above_ema20_pct.toFixed(0)}%
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-16 text-xs text-muted-foreground">EMA 50</span>
              <div className="flex-1">
                <ProgressBar
                  value={breadth.above_ema50_pct}
                  colorClass={breadth.above_ema50_pct > 60 ? "bg-green-400" : breadth.above_ema50_pct > 40 ? "bg-yellow-400" : "bg-red-400"}
                />
              </div>
              <span className={`w-10 text-right text-xs font-medium ${breadth.above_ema50_pct > 60 ? "text-green-400" : breadth.above_ema50_pct > 40 ? "text-yellow-400" : "bg-red-400"}`}>
                {breadth.above_ema50_pct.toFixed(0)}%
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-16 text-xs text-muted-foreground">EMA 200</span>
              <div className="flex-1">
                <ProgressBar
                  value={breadth.above_ema200_pct}
                  colorClass={breadth.above_ema200_pct > 60 ? "bg-green-400" : breadth.above_ema200_pct > 40 ? "bg-yellow-400" : "bg-red-400"}
                />
              </div>
              <span className={`w-10 text-right text-xs font-medium ${breadth.above_ema200_pct > 60 ? "text-green-400" : breadth.above_ema200_pct > 40 ? "text-yellow-400" : "text-red-400"}`}>
                {breadth.above_ema200_pct.toFixed(0)}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
