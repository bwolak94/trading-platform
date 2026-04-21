import { useQuery } from "@tanstack/react-query";
import { fetchFundingRatesEnhanced } from "../../api/client";
import type { FundingRateEntry } from "../../api/client";

interface FundingCellProps {
  symbol: string;
  rate: number;
}

function FundingCell({ symbol, rate }: FundingCellProps) {
  const ratePct = (rate * 100).toFixed(4);
  const isExtremelyLong = rate > 0.001;
  const isExtremelyShort = rate < -0.0005;
  const isLong = rate > 0.0003;
  const isShort = rate < 0;

  const bg = isExtremelyLong
    ? "bg-red-500/40 border-red-500/40 text-red-200"
    : isLong
      ? "bg-orange-500/20 border-orange-500/20 text-orange-200"
      : isExtremelyShort
        ? "bg-blue-500/40 border-blue-500/40 text-blue-200"
        : isShort
          ? "bg-blue-500/15 border-blue-500/15 text-blue-300"
          : "bg-border/20 border-border/30 text-muted-foreground";

  return (
    <div
      className={`flex flex-col items-center rounded border p-1.5 text-center ${bg}`}
      title={`${symbol}: ${ratePct}% funding rate`}
    >
      <span className="text-xs font-medium leading-none">
        {symbol.replace("USDT", "")}
      </span>
      <span className="mt-0.5 font-mono text-xs">{ratePct}%</span>
    </div>
  );
}

function formatSymbolList(entries: FundingRateEntry[], limit: number): string {
  const names = entries.slice(0, limit).map((r) => r.symbol.replace("USDT", ""));
  const remainder = entries.length - limit;
  return remainder > 0 ? `${names.join(", ")} +${remainder} more` : names.join(", ");
}

export function FundingHeatmapPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["funding-rates-enhanced"],
    queryFn: fetchFundingRatesEnhanced,
    refetchInterval: 5 * 60_000,
  });

  const rates = data?.rates ?? [];
  // Sort by funding rate descending (most positive = most crowded longs first)
  const sorted = [...rates].sort((a, b) => b.funding_rate - a.funding_rate).slice(0, 40);

  const hasExtremes =
    (data?.extreme_longs.length ?? 0) > 0 || (data?.extreme_shorts.length ?? 0) > 0;

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">Funding Rate Heatmap</h2>
          <p className="text-xs text-muted-foreground">
            Red = extreme long crowding · Blue = extreme short crowding
          </p>
        </div>
        {data && (
          <div className="flex gap-2 text-xs">
            <span className="text-red-400">
              {data.extreme_longs.length} extreme long
            </span>
            <span className="text-blue-400">
              {data.extreme_shorts.length} extreme short
            </span>
          </div>
        )}
      </div>

      {isLoading ? (
        <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
          Loading funding rates...
        </div>
      ) : sorted.length === 0 ? (
        <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
          No data available
        </div>
      ) : (
        <div className="grid grid-cols-5 gap-1 sm:grid-cols-8 lg:grid-cols-10">
          {sorted.map((item) => (
            <FundingCell key={item.symbol} symbol={item.symbol} rate={item.funding_rate} />
          ))}
        </div>
      )}

      {data && hasExtremes && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-400">
          {data.extreme_longs.length > 0 && (
            <span>
              Extreme long crowding: {formatSymbolList(data.extreme_longs, 3)}.{" "}
            </span>
          )}
          {data.extreme_shorts.length > 0 && (
            <span>
              Extreme shorts: {formatSymbolList(data.extreme_shorts, 3)}.
            </span>
          )}
        </div>
      )}
    </div>
  );
}
