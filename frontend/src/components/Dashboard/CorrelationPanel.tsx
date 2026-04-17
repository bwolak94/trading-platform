import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { fetchCorrelations, type CorrelationData } from "../../api/client";

const DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];

interface CorrelationPanelProps {
  symbols?: string[];
  timeframe?: string;
  lookbackDays?: number;
}

function getCorrelationColor(value: number): string {
  if (value >= 0.7) return "bg-green-600 text-white";
  if (value >= 0.4) return "bg-green-800/60 text-green-200";
  if (value >= 0.1) return "bg-green-900/30 text-green-300";
  if (value > -0.1) return "bg-gray-800 text-gray-300";
  if (value > -0.4) return "bg-red-900/30 text-red-300";
  if (value > -0.7) return "bg-red-800/60 text-red-200";
  return "bg-red-600 text-white";
}

function formatSymbol(symbol: string): string {
  return symbol.replace("USDT", "");
}

export function CorrelationPanel({
  symbols = DEFAULT_SYMBOLS,
  timeframe = "1h",
  lookbackDays = 30,
}: CorrelationPanelProps) {
  const symbolsParam = useMemo(() => symbols.join(","), [symbols]);

  const { data, isLoading, isError } = useQuery<CorrelationData>({
    queryKey: ["correlations", symbolsParam, timeframe, lookbackDays],
    queryFn: () => fetchCorrelations(symbolsParam, timeframe, lookbackDays),
    refetchInterval: 120_000,
  });

  const displaySymbols = data?.symbols ?? symbols;
  const matrix = data?.matrix;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-gray-500">
          Correlation Matrix
        </h2>
        <span className="text-xs text-gray-600">
          {lookbackDays}d / {timeframe}
        </span>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 py-4 text-sm text-gray-400">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading correlation data...
        </div>
      )}

      {isError && (
        <p className="text-sm text-bearish">Failed to load correlation data</p>
      )}

      {matrix && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse" role="grid" aria-label="Asset correlation matrix">
            <thead>
              <tr>
                <th className="p-1 text-xs text-gray-500" aria-label="Symbol" />
                {displaySymbols.map((sym) => (
                  <th key={sym} className="p-1 text-center text-xs font-medium text-gray-400">
                    {formatSymbol(sym)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displaySymbols.map((rowSym, rowIdx) => (
                <tr key={rowSym}>
                  <td className="p-1 text-right text-xs font-medium text-gray-400">
                    {formatSymbol(rowSym)}
                  </td>
                  {displaySymbols.map((colSym, colIdx) => {
                    const value = matrix[rowIdx]?.[colIdx] ?? 0;
                    const isDiagonal = rowIdx === colIdx;
                    return (
                      <td
                        key={colSym}
                        className={`p-1 text-center font-mono text-xs ${
                          isDiagonal
                            ? "bg-accent/20 text-accent"
                            : getCorrelationColor(value)
                        } rounded`}
                        title={`${formatSymbol(rowSym)} / ${formatSymbol(colSym)}: ${value.toFixed(3)}`}
                        aria-label={`${formatSymbol(rowSym)} to ${formatSymbol(colSym)} correlation: ${value.toFixed(2)}`}
                      >
                        {isDiagonal ? "1.00" : value.toFixed(2)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>

          {/* Legend */}
          <div className="mt-3 flex items-center justify-center gap-1 text-xs text-gray-500">
            <span className="inline-block h-3 w-3 rounded bg-red-600" />
            <span>-1.0</span>
            <span className="inline-block h-3 w-3 rounded bg-red-900/30" />
            <span className="inline-block h-3 w-3 rounded bg-gray-800" />
            <span>0</span>
            <span className="inline-block h-3 w-3 rounded bg-green-900/30" />
            <span className="inline-block h-3 w-3 rounded bg-green-600" />
            <span>+1.0</span>
          </div>
        </div>
      )}
    </div>
  );
}
