/**
 * Multi-Timeframe Signal Matrix
 * Grid: rows = assets, columns = timeframes
 * Each cell shows signal direction and confidence
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

interface MTFCell {
  direction: "LONG" | "SHORT" | "NEUTRAL";
  confidence: number;
  strategy: string;
  regime: string;
}

interface MTFMatrixData {
  assets: string[];
  timeframes: string[];
  matrix: Record<string, Record<string, MTFCell | null>>;
}

interface MTFSignalMatrixProps {
  onAssetSelect?: (asset: string, timeframe: string) => void;
}

const ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];
const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];

async function fetchMTFMatrix(): Promise<MTFMatrixData> {
  const { data } = await axios.get<MTFMatrixData>("/api/v1/mtf-matrix", {
    params: {
      assets: ASSETS.join(","),
      timeframes: TIMEFRAMES.join(","),
    },
  });
  return data;
}

function DirectionIcon({ direction }: { direction: "LONG" | "SHORT" | "NEUTRAL" }) {
  if (direction === "LONG") return <span aria-label="Long signal">▲</span>;
  if (direction === "SHORT") return <span aria-label="Short signal">▼</span>;
  return <span aria-label="Neutral signal">●</span>;
}

function CellSkeleton() {
  return <div className="h-12 animate-pulse rounded bg-white/5" />;
}

function SignalCell({
  cell,
  asset,
  timeframe,
  onAssetSelect,
}: {
  cell: MTFCell | null;
  asset: string;
  timeframe: string;
  onAssetSelect?: (asset: string, timeframe: string) => void;
}) {
  const [showTooltip, setShowTooltip] = useState(false);

  const handleClick = useCallback(() => {
    onAssetSelect?.(asset, timeframe);
  }, [asset, timeframe, onAssetSelect]);

  if (!cell) {
    return (
      <div className="flex h-12 items-center justify-center rounded border border-border/30 bg-surface/40 text-xs text-gray-600">
        —
      </div>
    );
  }

  const bgColor =
    cell.direction === "LONG"
      ? "bg-bullish/10 border-bullish/30 hover:bg-bullish/20"
      : cell.direction === "SHORT"
        ? "bg-bearish/10 border-bearish/30 hover:bg-bearish/20"
        : "bg-white/5 border-border/30 hover:bg-white/10";

  const textColor =
    cell.direction === "LONG"
      ? "text-bullish"
      : cell.direction === "SHORT"
        ? "text-bearish"
        : "text-gray-400";

  return (
    <div className="relative">
      <button
        type="button"
        onClick={handleClick}
        onMouseEnter={() => { setShowTooltip(true); }}
        onMouseLeave={() => { setShowTooltip(false); }}
        onFocus={() => { setShowTooltip(true); }}
        onBlur={() => { setShowTooltip(false); }}
        className={`flex h-12 w-full flex-col items-center justify-center gap-0.5 rounded border text-xs font-medium transition-colors ${bgColor} ${textColor}`}
        aria-label={`${asset} ${timeframe}: ${cell.direction} signal with ${cell.confidence}% confidence`}
      >
        <DirectionIcon direction={cell.direction} />
        <span className="text-[10px] opacity-80">{cell.confidence}%</span>
      </button>

      {showTooltip && (
        <div
          className="absolute bottom-full left-1/2 z-50 mb-2 w-44 -translate-x-1/2 rounded border border-border bg-surface p-2 text-xs shadow-xl"
          role="tooltip"
        >
          <p className="font-medium text-white">
            {asset} / {timeframe}
          </p>
          <p className={`mt-0.5 ${textColor}`}>
            Direction: {cell.direction}
          </p>
          <p className="text-gray-400">Confidence: {cell.confidence}%</p>
          <p className="text-gray-400">Strategy: {cell.strategy}</p>
          <p className="text-gray-400">Regime: {cell.regime}</p>
        </div>
      )}
    </div>
  );
}

function buildFallbackData(): MTFMatrixData {
  const matrix: Record<string, Record<string, MTFCell | null>> = {};
  for (const asset of ASSETS) {
    matrix[asset] = {};
    for (const tf of TIMEFRAMES) {
      matrix[asset][tf] = null;
    }
  }
  return { assets: ASSETS, timeframes: TIMEFRAMES, matrix };
}

export function MTFSignalMatrix({ onAssetSelect }: MTFSignalMatrixProps) {
  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ["mtf-matrix"],
    queryFn: fetchMTFMatrix,
    refetchInterval: 60_000,
    retry: false,
    placeholderData: buildFallbackData(),
  });

  const matrixData = data ?? buildFallbackData();
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Multi-Timeframe Signal Matrix</h2>
          {lastUpdated && (
            <p className="mt-0.5 text-xs text-gray-500">Updated: {lastUpdated}</p>
          )}
        </div>
        {isError && (
          <span className="rounded bg-bearish/10 px-2 py-0.5 text-xs text-bearish">
            Offline
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[500px] border-separate border-spacing-1">
          <thead>
            <tr>
              <th className="w-20 text-left text-xs font-medium text-gray-500">Asset</th>
              {TIMEFRAMES.map((tf) => (
                <th key={tf} className="text-center text-xs font-medium text-gray-400">
                  {tf}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ASSETS.map((asset) => (
              <tr key={asset}>
                <td className="py-0.5 pr-2 text-xs font-medium text-gray-300">
                  {asset.replace("USDT", "")}
                </td>
                {TIMEFRAMES.map((tf) => (
                  <td key={tf} className="py-0.5">
                    {isLoading ? (
                      <CellSkeleton />
                    ) : (
                      <SignalCell
                        cell={matrixData.matrix[asset]?.[tf] ?? null}
                        asset={asset}
                        timeframe={tf}
                        onAssetSelect={onAssetSelect}
                      />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1">
          <span className="text-bullish">▲</span> LONG
        </span>
        <span className="flex items-center gap-1">
          <span className="text-bearish">▼</span> SHORT
        </span>
        <span className="flex items-center gap-1">
          <span>●</span> NEUTRAL
        </span>
      </div>
    </div>
  );
}
