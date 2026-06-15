import { useQuery } from "@tanstack/react-query";
import { fetchFundingRates, type FundingRateData } from "../../api/client";

interface FundingRatePanelProps {
  symbols?: string;
}

function formatFundingRate(rate: number): string {
  return `${(rate * 100).toFixed(4)}%`;
}

function getFundingRateColor(rate: number): string {
  if (rate > 0.0005) return "text-green-400";
  if (rate > 0) return "text-green-600";
  if (rate === 0) return "text-gray-400";
  if (rate > -0.0005) return "text-red-600";
  return "text-red-400";
}

function formatNextFunding(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();

  if (diffMs <= 0) return "Now";

  const hours = Math.floor(diffMs / 3_600_000);
  const minutes = Math.floor((diffMs % 3_600_000) / 60_000);
  return `${hours}h ${minutes}m`;
}

function formatSymbol(symbol: string): string {
  return symbol.replace("USDT", "");
}

export function FundingRatePanel({ symbols }: FundingRatePanelProps) {
  const { data, isLoading, isError } = useQuery<FundingRateData[]>({
    queryKey: ["fundingRates", symbols],
    queryFn: () => fetchFundingRates(symbols),
    refetchInterval: 60_000,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-gray-500">
        Funding Rates
      </h2>

      {isLoading && (
        <div className="flex items-center gap-2 py-4 text-sm text-gray-400">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading funding rates...
        </div>
      )}

      {isError && (
        <p className="text-sm text-bearish">Failed to load funding rates</p>
      )}

      {data && data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left" role="table" aria-label="Funding rates table">
            <thead>
              <tr className="border-b border-border text-xs text-gray-500">
                <th className="pb-2 pr-3 font-medium">Symbol</th>
                <th className="pb-2 pr-3 text-right font-medium">Rate</th>
                <th className="pb-2 pr-3 text-right font-medium">Next</th>
                <th className="pb-2 text-right font-medium">Mark Price</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item) => (
                <tr key={item.symbol} className="border-b border-border/50 last:border-0">
                  <td className="py-2 pr-3">
                    <span className="font-mono text-xs font-medium text-white">
                      {formatSymbol(item.symbol)}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-right">
                    <span className={`font-mono text-xs font-semibold ${getFundingRateColor(item.funding_rate)}`}>
                      {formatFundingRate(item.funding_rate)}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-right">
                    <span className="font-mono text-xs text-gray-400">
                      {formatNextFunding(item.next_funding_time)}
                    </span>
                  </td>
                  <td className="py-2 text-right">
                    <span className="font-mono text-xs text-gray-300">
                      ${item.mark_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data?.length === 0 && (
        <p className="text-sm text-gray-500">No funding rate data available</p>
      )}
    </div>
  );
}
