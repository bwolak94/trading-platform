/**
 * B11: Portfolio Heat Map
 *
 * Treemap of all open positions coloured by unrealized P&L%.
 * Cell size = position size (exposure). Red = loss, green = gain.
 */

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Treemap, ResponsiveContainer, Tooltip } from "recharts";

interface OpenPosition {
  asset: string;
  direction: string;
  exposure_pct: number;
  unrealized_pnl_pct: number;
}

async function fetchOpenPositions(): Promise<OpenPosition[]> {
  const resp = await fetch("/api/v1/simulation/positions?status=OPEN");
  if (!resp.ok) throw new Error("Failed to fetch open positions");
  return resp.json();
}

function pnlColor(pnl: number): string {
  if (pnl > 2) return "#16a34a";
  if (pnl > 0) return "#22c55e";
  if (pnl > -2) return "#ef4444";
  return "#991b1b";
}

interface TreemapContentProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  pnl?: number;
  direction?: string;
}

function CustomContent({ x = 0, y = 0, width = 0, height = 0, name, pnl = 0, direction }: TreemapContentProps) {
  if (width < 30 || height < 20) return null;
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={pnlColor(pnl)} rx={4} />
      <text
        x={x + width / 2}
        y={y + height / 2 - 6}
        textAnchor="middle"
        fill="white"
        fontSize={Math.min(12, width / 6)}
        fontWeight="600"
      >
        {name}
      </text>
      <text
        x={x + width / 2}
        y={y + height / 2 + 8}
        textAnchor="middle"
        fill="rgba(255,255,255,0.8)"
        fontSize={Math.min(10, width / 7)}
      >
        {direction} {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}%
      </text>
    </g>
  );
}

export function PortfolioHeatMap() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["portfolio-heatmap"],
    queryFn: fetchOpenPositions,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const treeData = useMemo(() => {
    if (!data) return [];
    return data.map((p) => ({
      name: p.asset.replace("/USDT", ""),
      size: Math.max(p.exposure_pct, 0.5),
      pnl: p.unrealized_pnl_pct,
      direction: p.direction,
    }));
  }, [data]);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-gray-200">Portfolio Heat Map</h3>
        <p className="text-xs text-gray-400">
          Open positions by size — colour = unrealized P&L%
        </p>
      </div>

      {isLoading && (
        <div className="flex h-48 items-center justify-center text-xs text-gray-500">Loading…</div>
      )}
      {isError && (
        <div className="flex h-48 items-center justify-center text-xs text-bearish">Failed to load positions</div>
      )}

      {!isLoading && !isError && treeData.length === 0 && (
        <div className="flex h-48 items-center justify-center text-xs text-gray-500">
          No open positions
        </div>
      )}

      {!isLoading && !isError && treeData.length > 0 && (
        <ResponsiveContainer width="100%" height={220}>
          <Treemap
            data={treeData}
            dataKey="size"
            content={<CustomContent />}
          >
            <Tooltip
              contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
              formatter={(value: number, _name: string, props) => [
                `${props.payload.pnl >= 0 ? "+" : ""}${props.payload.pnl.toFixed(2)}%`,
                `P&L (size: ${value.toFixed(1)}%)`,
              ]}
            />
          </Treemap>
        </ResponsiveContainer>
      )}
    </div>
  );
}
