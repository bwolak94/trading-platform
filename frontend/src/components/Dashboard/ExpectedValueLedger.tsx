/**
 * B3: Expected Value Ledger
 *
 * EV = (win_rate × avg_win) − (loss_rate × avg_loss)
 * Per asset and per strategy, updated each time a position closes.
 */

import { useQuery } from "@tanstack/react-query";

interface EVRow {
  asset: string;
  strategy: string;
  win_rate: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  ev_pct: number;
  sample_size: number;
}

async function fetchEVData(): Promise<EVRow[]> {
  const resp = await fetch("/api/v1/analytics/expected-value");
  if (!resp.ok) throw new Error("Failed to fetch EV data");
  return resp.json();
}

function EVBadge({ value }: { readonly value: number }) {
  const color = value > 0 ? "text-bullish" : value < 0 ? "text-bearish" : "text-gray-400";
  return <span className={`font-mono font-semibold ${color}`}>{value > 0 ? "+" : ""}{value.toFixed(2)}%</span>;
}

export function ExpectedValueLedger() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["expected-value-ledger"],
    queryFn: fetchEVData,
    staleTime: 2 * 60 * 1000,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold text-gray-200">Expected Value Ledger</h3>
      <p className="mb-3 text-xs text-gray-400">
        EV = (win_rate × avg_win) − (loss_rate × avg_loss) per asset and strategy
      </p>

      {isLoading && (
        <div className="flex h-32 items-center justify-center text-xs text-gray-500">Loading…</div>
      )}
      {isError && (
        <div className="flex h-32 items-center justify-center text-xs text-bearish">Failed to load EV data</div>
      )}

      {!isLoading && !isError && data && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-gray-500">
                <th className="pb-2 text-left font-medium">Asset</th>
                <th className="pb-2 text-left font-medium">Strategy</th>
                <th className="pb-2 text-right font-medium">Win%</th>
                <th className="pb-2 text-right font-medium">Avg Win</th>
                <th className="pb-2 text-right font-medium">Avg Loss</th>
                <th className="pb-2 text-right font-medium">EV</th>
                <th className="pb-2 text-right font-medium">N</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr key={i} className="border-b border-border/50 last:border-0">
                  <td className="py-1.5 font-medium text-gray-200">{row.asset}</td>
                  <td className="py-1.5 text-gray-400">{row.strategy}</td>
                  <td className="py-1.5 text-right text-gray-300">{(row.win_rate * 100).toFixed(1)}%</td>
                  <td className="py-1.5 text-right text-bullish">+{row.avg_win_pct.toFixed(2)}%</td>
                  <td className="py-1.5 text-right text-bearish">-{row.avg_loss_pct.toFixed(2)}%</td>
                  <td className="py-1.5 text-right"><EVBadge value={row.ev_pct} /></td>
                  <td className="py-1.5 text-right text-gray-500">{row.sample_size}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.length === 0 && (
            <div className="py-8 text-center text-xs text-gray-500">No closed positions yet</div>
          )}
        </div>
      )}
    </div>
  );
}
