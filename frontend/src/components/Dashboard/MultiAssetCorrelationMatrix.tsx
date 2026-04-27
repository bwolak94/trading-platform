/**
 * Multi-Asset Correlation Matrix
 * Live NxN heatmap of rolling 24h Pearson correlations between tracked symbols.
 * Flashes red when correlation spikes above 0.9 (contagion risk).
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";

const SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "AVAX", "LINK"];
const PAIRS = SYMBOLS.map((s) => `${s}USDT`);

interface OHLCVBar {
  close: number;
}

async function fetchCloses(symbol: string): Promise<number[]> {
  const { data } = await axios.get(
    `/api/v1/market/ohlcv?symbol=${symbol}&timeframe=1h&limit=24`,
  );
  const bars: OHLCVBar[] = Array.isArray(data) ? data : (data?.data ?? []);
  return bars.map((b) => b.close);
}

function pearson(a: number[], b: number[]): number {
  const n = Math.min(a.length, b.length);
  if (n < 3) return 0;
  const meanA = a.slice(0, n).reduce((s, v) => s + v, 0) / n;
  const meanB = b.slice(0, n).reduce((s, v) => s + v, 0) / n;
  let num = 0, da2 = 0, db2 = 0;
  for (let i = 0; i < n; i++) {
    const da = (a[i] ?? 0) - meanA;
    const db = (b[i] ?? 0) - meanB;
    num += da * db;
    da2 += da * da;
    db2 += db * db;
  }
  const denom = Math.sqrt(da2 * db2);
  return denom === 0 ? 0 : num / denom;
}

function corrColor(r: number): string {
  const abs = Math.abs(r);
  if (r === 1) return "bg-white/10 text-white";
  if (abs >= 0.9) return "bg-bearish/70 text-white font-bold";
  if (abs >= 0.7) return "bg-bearish/40 text-bearish";
  if (abs >= 0.5) return "bg-amber-500/30 text-amber-400";
  if (abs >= 0.3) return "bg-white/8 text-gray-400";
  return "bg-white/3 text-gray-600";
}

export function MultiAssetCorrelationMatrix() {
  const [selectedPair, setSelectedPair] = useState<{ a: string; b: string } | null>(null);

  const queries = PAIRS.map((pair) =>
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useQuery({
      queryKey: ["corr-closes", pair],
      queryFn: () => fetchCloses(pair),
      staleTime: 120_000,
      refetchInterval: 120_000,
      retry: false,
    }),
  );

  const closeMap = useMemo(() => {
    const m: Record<string, number[]> = {};
    queries.forEach((q, i) => {
      const sym = SYMBOLS[i];
      if (sym && q.data && q.data.length > 0) m[sym] = q.data;
    });
    return m;
  }, [queries]);

  const matrix = useMemo(() => {
    const m: Record<string, Record<string, number>> = {};
    for (const a of SYMBOLS) {
      m[a] = {};
      for (const b of SYMBOLS) {
        const closesA = closeMap[a];
        const closesB = closeMap[b];
        if (a === b) {
          m[a][b] = 1;
        } else if (closesA && closesB) {
          m[a][b] = parseFloat(pearson(closesA, closesB).toFixed(2));
        } else {
          m[a][b] = 0;
        }
      }
    }
    return m;
  }, [closeMap]);

  // Detect contagion pairs (|corr| >= 0.9, excluding diagonal)
  const contagionPairs = useMemo(() => {
    const pairs: { a: string; b: string; r: number }[] = [];
    for (let i = 0; i < SYMBOLS.length; i++) {
      for (let j = i + 1; j < SYMBOLS.length; j++) {
        const symA = SYMBOLS[i];
        const symB = SYMBOLS[j];
        if (!symA || !symB) continue;
        const r = matrix[symA]?.[symB] ?? 0;
        if (Math.abs(r) >= 0.9) pairs.push({ a: symA, b: symB, r });
      }
    }
    return pairs;
  }, [matrix]);

  const isLoading = queries.some((q) => q.isLoading);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Correlation Matrix</h2>
        {contagionPairs.length > 0 && (
          <span className="animate-pulse rounded bg-bearish/20 px-2 py-0.5 text-xs font-bold text-bearish">
            {contagionPairs.length} contagion pair{contagionPairs.length > 1 ? "s" : ""}
          </span>
        )}
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        Rolling 24h Pearson correlations. Red ≥ 0.9 = contagion risk (diversification breaks down).
      </p>

      {isLoading ? (
        <div className="h-40 animate-pulse rounded bg-white/5" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-0.5 text-[9px]">
            <thead>
              <tr>
                <th className="w-8 text-gray-600" />
                {SYMBOLS.map((s) => (
                  <th key={s} className="text-center font-medium text-gray-500 pb-1">{s}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SYMBOLS.map((rowSym) => (
                <tr key={rowSym}>
                  <td className="pr-1 text-right text-gray-500 font-medium">{rowSym}</td>
                  {SYMBOLS.map((colSym) => {
                    const r = matrix[rowSym]?.[colSym] ?? 0;
                    const isSelected = selectedPair?.a === rowSym && selectedPair.b === colSym;
                    return (
                      <td
                        key={colSym}
                        className={`h-6 w-8 rounded-[1px] text-center cursor-default transition-opacity ${corrColor(r)} ${isSelected ? "ring-1 ring-white/50" : ""}`}
                        title={`${rowSym}/${colSym}: ${r.toFixed(2)}`}
                        onClick={() => setSelectedPair(rowSym === colSym ? null : { a: rowSym, b: colSym })}
                      >
                        {r.toFixed(2)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 flex flex-wrap gap-2 text-[9px] text-gray-500">
            <span className="flex items-center gap-1"><span className="inline-block h-2 w-3 rounded bg-bearish/70" />≥0.9 contagion</span>
            <span className="flex items-center gap-1"><span className="inline-block h-2 w-3 rounded bg-bearish/40" />≥0.7 high</span>
            <span className="flex items-center gap-1"><span className="inline-block h-2 w-3 rounded bg-amber-500/30" />≥0.5 moderate</span>
            <span className="flex items-center gap-1"><span className="inline-block h-2 w-3 rounded bg-white/8" />low</span>
          </div>
        </div>
      )}
    </div>
  );
}
