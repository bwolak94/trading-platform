/**
 * B6: Parameter Sensitivity Heatmap
 *
 * 2D heatmap of Sharpe vs two parameters (e.g. EMA fast/slow periods).
 * Calls backend /benchmark/sensitivity endpoint.
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

interface SensitivityCell {
  param1: number;
  param2: number;
  sharpe: number;
}

interface SensitivityData {
  param1_name: string;
  param2_name: string;
  param1_values: number[];
  param2_values: number[];
  cells: SensitivityCell[];
}

async function fetchSensitivity(
  symbol: string,
  param1: string,
  param2: string,
): Promise<SensitivityData> {
  const resp = await fetch(
    `/api/v1/benchmark/sensitivity?symbol=${symbol}&param1=${param1}&param2=${param2}`,
  );
  if (!resp.ok) throw new Error("Failed to fetch sensitivity data");
  return resp.json();
}

function getHeatColor(sharpe: number, min: number, max: number): string {
  const norm = max === min ? 0.5 : (sharpe - min) / (max - min);
  const r = Math.round(255 * (1 - norm));
  const g = Math.round(255 * norm);
  return `rgb(${r},${g},60)`;
}

export function ParameterSensitivityHeatmap() {
  const [symbol, setSymbol] = useState("BTC/USDT");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["param-sensitivity", symbol],
    queryFn: () => fetchSensitivity(symbol, "ema_fast", "ema_slow"),
    staleTime: 10 * 60 * 1000,
    enabled: !!symbol,
  });

  const { minSharpe, maxSharpe, cellMap } = useMemo(() => {
    if (!data) return { minSharpe: 0, maxSharpe: 1, cellMap: new Map<string, number>() };
    const sharpes = data.cells.map((c) => c.sharpe);
    const map = new Map(data.cells.map((c) => [`${c.param1}:${c.param2}`, c.sharpe]));
    return {
      minSharpe: Math.min(...sharpes),
      maxSharpe: Math.max(...sharpes),
      cellMap: map,
    };
  }, [data]);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Parameter Sensitivity Heatmap</h3>
          <p className="text-xs text-gray-400">Sharpe ratio vs EMA fast/slow periods</p>
        </div>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300"
          aria-label="Select asset"
        >
          <option value="BTC/USDT">BTC/USDT</option>
          <option value="ETH/USDT">ETH/USDT</option>
          <option value="SOL/USDT">SOL/USDT</option>
        </select>
      </div>

      {isLoading && (
        <div className="flex h-48 items-center justify-center text-xs text-gray-500">Loading…</div>
      )}
      {isError && (
        <div className="flex h-48 items-center justify-center text-xs text-bearish">
          Failed to load sensitivity data
        </div>
      )}

      {!isLoading && !isError && data && (
        <div className="overflow-x-auto">
          <div className="inline-block">
            <div className="mb-1 flex items-center gap-1">
              <span className="w-12 text-right text-[10px] text-gray-500" />
              {data.param2_values.map((v) => (
                <span key={v} className="w-9 text-center text-[10px] text-gray-500">{v}</span>
              ))}
            </div>
            <div className="mb-1 text-[10px] text-gray-500 ml-12">{data.param2_name} →</div>
            {data.param1_values.map((p1) => (
              <div key={p1} className="flex items-center gap-1 mb-0.5">
                <span className="w-12 text-right text-[10px] text-gray-500">{p1}</span>
                {data.param2_values.map((p2) => {
                  const sharpe = cellMap.get(`${p1}:${p2}`) ?? 0;
                  return (
                    <div
                      key={p2}
                      title={`${data.param1_name}=${p1}, ${data.param2_name}=${p2}: Sharpe ${sharpe.toFixed(2)}`}
                      className="h-9 w-9 rounded-sm flex items-center justify-center text-[9px] font-mono text-white/80"
                      style={{ background: getHeatColor(sharpe, minSharpe, maxSharpe) }}
                    >
                      {sharpe.toFixed(1)}
                    </div>
                  );
                })}
              </div>
            ))}
            <div className="mt-1 text-[10px] text-gray-500">{data.param1_name} ↓</div>
          </div>
        </div>
      )}
    </div>
  );
}
